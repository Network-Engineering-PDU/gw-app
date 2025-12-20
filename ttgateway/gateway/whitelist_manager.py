import logging
from ttgateway.utils import non_periodic_task


logger = logging.getLogger(__name__)


class WhitelistManager:
    """ WhitelistManager is responsible for managing the process of adding nodes
    to a whitelist and reassigning nodes to different gateways in a network
    based on specific events.

    It maintains lists of whitelist candidates and
    reassignment tasks, updating them as events occur. The class includes
    methods for updating candidates, choosing the best gateway for a node based
    on signal strength (RSSI) and time-to-live (TTL) values, and handling the
    reassignment of nodes to new gateways when necessary. Additionally, it
    provides callback functions to handle updates and reassignments, and checks
    if an event is valid for processing. This helps optimize network performance
    by ensuring nodes are connected to the most appropriate gateways.
    """

    WAIT_TIME = 2 # 2 seconds

    def __init__(self):
        """ Initializes a WhitelistManager instance.
        """
        self.wl_candidates = []
        self.wl_reassigns = []

    def update_candidate(self, event):
        """ Updates the whitelist candidate based on the given event.

        When an event is received from a node that is not assigned to any
        gateway, an assignment process is initiated for that node. During the
        allocation time, the events received by the different gateways of that
        node are stored.

        :param event: The event triggering the update.
        :type event: class:`~ttgateway.events.Event`
        """
        if not self.event_is_assignable(event):
            return
        whitelist_candidate = None
        for candidate in self.wl_candidates:
            if event.node == candidate.event.node:
                whitelist_candidate = candidate
                break
        if whitelist_candidate:
            if event.event_type == whitelist_candidate.event.event_type:
                if event.gw not in whitelist_candidate.gateways:
                    whitelist_candidate.update(event.gw, event.data["rssi"],
                        event.data["ttl"])
        else:
            whitelist_candidate = WhitelistCandidate(event, self.update_cb,
                self.WAIT_TIME)
            self.wl_candidates.append(whitelist_candidate)
            whitelist_candidate.update(event.gw, event.data["rssi"],
                event.data["ttl"])

    def update_cb(self, wl_candidate):
        """ Callback function to handle the update of a whitelist candidate.

        After the assignation time has elapsed, the gateway with the best
        coverage is selected and the node is added to its whitelist.

        :param wl_candidate: The whitelist candidate to update.
        :type wl_candidate:
            class:`~ttgateway.gateway.whitelist_manager.WhitelistCandidate`
        """
        chosen_gw = self.choose_gw(wl_candidate)
        chosen_gw.add_node_to_whitelist(wl_candidate.event.node)
        self.wl_candidates.remove(wl_candidate)
        wl_candidate.event.gw.event_handler.add_event(wl_candidate.event)

    def choose_gw(self, wl_candidate):
        """ Chooses the gateway with the highest TTL and RSSI for the whitelist
        candidate.

        :param wl_candidate: The whitelist candidate for which to choose the
            gateway.
        :type wl_candidate:
            class:`~ttgateway.gateway.whitelist_manager.WhitelistCandidate`

        :return: The chosen gateway.
        :rtype: class:`~ttgwlib.gateway.Gateway`
        """
        gateways = wl_candidate.gateways
        highest_ttl = max(gateways.values(), key=lambda x: x["ttl"])["ttl"]
        valid_gws = [k for k, v in gateways.items() if v["ttl"] == highest_ttl]
        chosen_gw = max(valid_gws, key=lambda x: gateways[x]["rssi"])
        return chosen_gw

    def reassign_node(self, event, gateway):
        """ Reassigns a node to a different gateway based on the given event.

        If messages from a node are not received by the gateway assigned to it,
        but are received by a gateway that is not assigned to it, a
        re-assignment process is started.

        :param event: The event triggering the reassignment.
        :type event: class:`~ttgateway.events.Event`
        :param gateway: The gateway to which the node is reassigned.
        :type gateway: class:`~ttgwlib.gateway.Gateway`
        """
        if not self.event_is_assignable(event):
            return
        whitelist_reassign = None
        for reassign in self.wl_reassigns:
            if event.node == reassign.event.node:
                whitelist_reassign = reassign
                break
        if not whitelist_reassign:
            whitelist_reassign = WhitelistReassign(event, gateway,
                self.reassign_cb, self.WAIT_TIME)
            self.wl_reassigns.append(whitelist_reassign)
        elif whitelist_reassign.wl_task.done():
            whitelist_reassign.restart_task(self.reassign_cb, self.WAIT_TIME)
        pending_events = whitelist_reassign.pending_events_get()
        if (len(pending_events) > 0 and
                event.data["sequence_number"] != \
                pending_events[0].data["sequence_number"]):
            whitelist_reassign.pending_events_clear()
        whitelist_reassign.pending_event_store(event)

    def reassign_cancel(self, event):
        """ Cancels the reassignment of a node based on the given event.

        :param event: The event triggering the cancellation.
        :type event: class:`~ttgateway.events.Event`
        """
        for reassign in self.wl_reassigns:
            if event.node == reassign.event.node:
                reassign.wl_task.cancel()
                self.wl_reassigns.remove(reassign)

    def reassign_cb(self, wl_reassign):
        """ Callback function to handle the reassignment of a node.

        If, after the re-assignment time, the gateway assigned to the sensor has
        not received the event from the node, the node is removed from the
        whitelist and the assignment process is repeated.

        :param wl_reassign: The whitelist reassignment to handle.
        :type wl_reassign: WhitelistReassign
        """
        if wl_reassign.loss_counter_get() <= 3:
            wl_reassign.loss_counter_inc()
            logger.debug(f"Node reassignment {wl_reassign.event.node} " + \
            f"counter: {wl_reassign.loss_counter_get()}")
            return
        logger.debug(f"Reassigning node {wl_reassign.event.node} from gw " + \
            f"{wl_reassign.gateway.id}")
        wl_reassign.gateway.gw.remove_node_from_whitelist(
            wl_reassign.event.node)
        self.wl_reassigns.remove(wl_reassign)
        for event in wl_reassign.pending_events:
            event.gw.event_handler.add_event(event)

    def event_is_assignable(self, event):
        """ Checks if the event is assignable based on its attributes.

        :param event: The event to check.
        :type event: class:`~ttgateway.events.Event`
        :return: True if the event is assignable, False otherwise.
        :rtype: bool
        """
        return (hasattr(event, "node") and event.node and hasattr(event, "gw")
            and event.gw and "rssi" in event.data and "ttl" in event.data and
            "sequence_number" in event.data)


class WhitelistCandidate:
    """ Represents a candidate for the whitelist.
    """
    def __init__(self, event, timeout_cb, timeout):
        """ Initializes a WhitelistCandidate instance.

        :param event: The event associated with the whitelist candidate.
        :type event: class:`~ttgateway.events.Event`

        :param timeout_cb: The callback function to call on timeout.
        :type timeout_cb: Callable

        :param timeout: The timeout value in seconds.
        :type timeout: integer
        """
        self.event = event
        self.gateways = {} # Dict[gateway, rssi]
        self.wl_task = non_periodic_task(timeout_cb, timeout, self)

    def update(self, gateway, rssi, ttl):
        """ Updates the RSSI and TTL values for a gateway.

        :param gateway: The gateway to update.
        :type gateway: class:`~ttgwlib.gateway.Gateway`

        :param rssi: The RSSI value.
        :type rssi: integer

        :param ttl: The TTL value.
        :type ttl: integer
        """
        self.gateways[gateway] = {
            "rssi": rssi,
            "ttl": ttl
        }


class WhitelistReassign:
    """ Represents a reassignment of a node to a different gateway.
    """
    def __init__(self, event, gateway, timeout_cb, timeout):
        """ Initializes a WhitelistReassign instance.

        :param event: The event associated with the whitelist reassignment.
        :type event: class:`~ttgateway.events.Event`

        :param gateway: The gateway to which the node is reassigned.
        :type gateway: class:`~ttgwlib.gateway.Gateway`

        :param timeout_cb: The callback function to call on timeout.
        :type timeout_cb: Callable

        :param timeout: The timeout value in seconds.
        :type timeout: integer
        """
        self.event = event
        self.gateway = gateway
        self.wl_task = non_periodic_task(timeout_cb, timeout, self)
        self.pending_events = []
        self.loss_counter = 0

    def restart_task(self, timeout_cb, timeout):
        self.wl_task = non_periodic_task(timeout_cb, timeout, self)

    def loss_counter_get(self):
        return self.loss_counter

    def loss_counter_inc(self):
        self.loss_counter += 1

    def pending_events_get(self):
        return self.pending_events

    def pending_event_store(self, event):
        self.pending_events.append(event)

    def pending_events_clear(self):
        self.pending_events.clear()
