import itertools

import six


class BaseManager(object):
    """Manage client connections.

    This class keeps track of all the clients and the rooms they are in, to
    support the broadcasting of messages. The data used by this class is
    stored in a memory structure, making it appropriate only for single process
    services. More sophisticated storage backends can be implemented by
    subclasses.
    """
    def __init__(self):
        self.server = None
        self.rooms = {}
        self.callbacks = {}

    def initialize(self, server):
        self.server = server

    def get_namespaces(self):
        """Return an iterable with the active namespace names."""
        return six.iterkeys(self.rooms)

    def get_participants(self, namespace, room):
        """Return an iterable with the active participants in a room."""
        for sid, active in six.iteritems(self.rooms[namespace][room].copy()):
            yield sid

    def connect(self, sid, namespace):
        """Register a client connection to a namespace."""
        self.enter_room(sid, namespace, None)
        self.enter_room(sid, namespace, sid)

    def is_connected(self, sid, namespace):
        try:
            return self.rooms[namespace][None][sid]
        except KeyError:
            pass

    def disconnect(self, sid, namespace):
        """Register a client disconnect from a namespace."""
        rooms = []
        for room_name, room in six.iteritems(self.rooms[namespace]):
            if sid in room:
                rooms.append(room_name)
        for room in rooms:
            self.leave_room(sid, namespace, room)
        if sid in self.callbacks and namespace in self.callbacks[sid]:
            del self.callbacks[sid][namespace]
            if len(self.callbacks[sid]) == 0:
                del self.callbacks[sid]

    def enter_room(self, sid, namespace, room):
        """Add a client to a room."""
        if namespace not in self.rooms:
            self.rooms[namespace] = {}
        if room not in self.rooms[namespace]:
            self.rooms[namespace][room] = {}
        self.rooms[namespace][room][sid] = True

    def leave_room(self, sid, namespace, room):
        """Remove a client from a room."""
        try:
            del self.rooms[namespace][room][sid]
            if len(self.rooms[namespace][room]) == 0:
                del self.rooms[namespace][room]
                if len(self.rooms[namespace]) == 0:
                    del self.rooms[namespace]
        except KeyError:
            pass

    def close_room(self, room, namespace):
        """Remove all participants from a room."""
        try:
            for sid in self.get_participants(namespace, room):
                self.leave_room(sid, namespace, room)
        except KeyError:
            pass

    def get_rooms(self, sid, namespace):
        """Return the rooms a client is in."""
        r = []
        try:
            for room_name, room in six.iteritems(self.rooms[namespace]):
                if room_name is not None and sid in room and room[sid]:
                    r.append(room_name)
        except KeyError:
            pass
        return r

    def emit(self, event, data, namespace, room=None, skip_sid=None,
             callback=None):
        """Emit a message to a single client, a room, or all the clients
        connected to the namespace."""
        if namespace not in self.rooms or room not in self.rooms[namespace]:
            return
        for sid in self.get_participants(namespace, room):
            if sid != skip_sid:
                if callback is not None:
                    id = self._generate_ack_id(sid, namespace, callback)
                else:
                    id = None
                self.server._emit_internal(sid, event, data, namespace, id)

    def trigger_callback(self, sid, namespace, id, data):
        """Invoke an application callback."""
        callback = None
        try:
            callback = self.callbacks[sid][namespace][id]
        except KeyError:
            # if we get an unknown callback we just ignore it
            self.server.logger.warning('Unknown callback received, ignoring.')
        else:
            del self.callbacks[sid][namespace][id]
        if callback is not None:
            callback(*data)

    def _generate_ack_id(self, sid, namespace, callback):
        """Generate a unique identifier for an ACK packet."""
        namespace = namespace or '/'
        if sid not in self.callbacks:
            self.callbacks[sid] = {}
        if namespace not in self.callbacks[sid]:
            self.callbacks[sid][namespace] = {0: itertools.count(1)}
        id = six.next(self.callbacks[sid][namespace][0])
        self.callbacks[sid][namespace][id] = callback
        return id
