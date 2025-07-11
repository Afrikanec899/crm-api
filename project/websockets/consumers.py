from django.utils import timezone

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from core.models.core import Account, AccountActivityLog, User

from .exceptions import ClientError


class MonitConsumer(AsyncJsonWebsocketConsumer):
    """
    activity monitor consumer
    """

    @database_sync_to_async
    def get_account(self):
        queryset = Account.objects.filter(id=self.scope["url_route"]["kwargs"]["account_id"])
        if self.scope["user"].role not in [User.MANAGER, User.ADMIN]:
            queryset = queryset.filter(manager=self.scope["user"])
        return queryset.first()

    @database_sync_to_async
    def start_track(self):
        now = timezone.now()
        return AccountActivityLog.objects.create(
            account=self.account, user=self.scope["user"], start_at=now, end_at=now
        ).uuid

    @database_sync_to_async
    def stop_track(self):
        AccountActivityLog.objects.filter(account=self.account, user=self.scope["user"], end_at__isnull=True).update(
            end_at=timezone.now()
        )

    @database_sync_to_async
    def track(self, session_id):
        AccountActivityLog.objects.filter(uuid=session_id).update(end_at=timezone.now())

    # WebSocket event handlers
    async def connect(self):
        """
        Called when the websocket is handshaking as part of initial connection.
        """
        # Are they logged in?
        if self.scope["user"].is_anonymous:
            # Reject the connection
            await self.close()
        else:
            self.account = await self.get_account()
            if not self.account:
                await self.close()

            else:
                # Accept the connection
                await self.accept()

                session_id = await self.start_track()
                # Send a message down to the client
                await self.send_json({'session_id': str(session_id)})

    async def receive_json(self, content, **kwargs):
        """
        Called when we get a text frame. Channels will JSON-decode the payload
        for us and pass it as the first argument.
        """
        # Messages will have a "command" key we can switch on
        session_id = content.get('session_id')
        await self.track(session_id)

    async def disconnect(self, code):
        """
        Called when the WebSocket closes for any reason.
        """
        await self.stop_track()


class EventsConsumer(AsyncJsonWebsocketConsumer):
    """
    This chat consumer handles websocket connections for chat clients.

    It uses AsyncJsonWebsocketConsumer, which means all the handling functions
    must be async functions, and any sync work (like ORM access) has to be
    behind database_sync_to_async or sync_to_async. For more, read
    http://channels.readthedocs.io/en/latest/topics/consumers.html
    """

    # WebSocket event handlers
    async def connect(self):
        """
        Called when the websocket is handshaking as part of initial connection.
        """
        # Are they logged in?
        if self.scope["user"].is_anonymous:
            # Reject the connection
            await self.close()
        else:
            # Accept the connection
            await self.accept()
        self.room_name = f'notifications_{self.scope["user"].id}'
        await self.channel_layer.group_add(self.room_name, self.channel_name)

        self.rooms = {self.room_name}

        await self.channel_layer.group_send(self.room_name, {"type": "notification", 'message': 'message'})

    async def disconnect(self, code):
        """
        Called when the WebSocket closes for any reason.
        """
        # Leave all the rooms we are still in
        # self.clients.discard(f'{self.channel_name}::{self.scope["user"].id}')
        for room_group_name in list(self.rooms):
            try:
                await self.leave_room(room_group_name)
            except ClientError:
                pass

    async def notification(self, event):
        await self.send_json(event)

    async def leave_room(self, room_name):
        """
        Called by receive_json when someone sent a leave command.
        """
        # Remove that we're in the room
        self.rooms.discard(room_name)
        # Remove them from the group so they no longer get room messages
        await self.channel_layer.group_discard(room_name, self.channel_name)
