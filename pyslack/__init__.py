import datetime
import logging
import requests


class SlackError(Exception):
    pass


class SlackClient(object):
    BASE_URL = 'https://slack.com/api'

    def __init__(self, token, verify=False):
        self.token = token
        self.verify = verify
        self.blocked_until = None
        self.channel_name_id_map = {}
        self.group_name_id_map = {}
        self.user_id_name_map = {}

    def _channel_is_name(self, channel):
        return channel.startswith('#')

    def _make_request(self, method, params, files=None):
        """Make request to API endpoint

        Note: Ignoring SSL cert validation due to intermittent failures
        http://requests.readthedocs.org/en/latest/user/advanced/#ssl-cert-verification
        """
        if self.blocked_until is not None and \
                        datetime.datetime.utcnow() < self.blocked_until:
            raise SlackError("Too many requests - wait until {0}" \
                             .format(self.blocked_until))

        url = "%s/%s" % (SlackClient.BASE_URL, method)
        params['token'] = self.token
        response = requests.post(url, data=params, verify=self.verify, files=files)

        if response.status_code == 429:
            # Too many requests
            retry_after = int(response.headers.get('retry-after', '1'))
            self.blocked_until = datetime.datetime.utcnow() + \
                                 datetime.timedelta(seconds=retry_after)
            raise SlackError("Too many requests - retry after {0} second(s)" \
                             .format(retry_after))

        result = response.json()
        if not result['ok']:
            raise SlackError(result['error'])
        return result

    def channels_list(self, exclude_archived=True, **params):
        """channels.list

        This method returns a list of all channels in the team. This includes
        channels the caller is in, channels they are not currently in, and
        archived channels. The number of (non-deactivated) members in each
        channel is also returned.

        https://api.slack.com/methods/channels.list
        """
        method = 'channels.list'
        params.update({'exclude_archived': exclude_archived and 1 or 0})
        return self._make_request(method, params)

    def channel_name_to_id(self, channel_name, force_lookup=False):
        """Helper name for getting a channel's id from its name
        """
        if force_lookup or not self.channel_name_id_map:
            channels = self.channels_list()['channels']
            self.channel_name_id_map = {channel['name']: channel['id'] for channel in channels}
        channel = channel_name.startswith('#') and channel_name[1:] or channel_name
        return self.channel_name_id_map.get(channel)

    def channel_history(self, channel, **params):
        method = 'channels.history'
        channel_id = self.channel_name_to_id(channel)
        params.update({
            'channel': channel_id,
        })
        return self._make_request(method, params)

    def groups_list(self, exclude_archived=True, **params):
        """groups.list
        This method returns a list of all groups in the team. This includes
        channels the caller is in, channels they are not currently in, and
        archived channels. The number of (non-deactivated) members in each
        channel is also returned.
        https://api.slack.com/methods/groups.list
        """
        method = 'groups.list'
        params.update({'exclude_archived': exclude_archived and 1 or 0})
        return self._make_request(method, params)

    def group_name_to_id(self, group_name, force_lookup=False):
        """Helper name for getting a group's id from its name
        """
        if force_lookup or not self.group_name_id_map:
            groups = self.groups_list()['groups']
            self.group_name_id_map = {group['name']: group['id'] for group in groups}
        group = group_name.startswith('#') and group_name[1:] or group_name
        return self.group_name_id_map.get(group)

    def group_history(self, group, **params):
        method = 'groups.history'
        group_id = self.group_name_to_id(group)
        params.update({
            'channel': group_id,
        })
        return self._make_request(method, params)

    def users_list(self, **params):
        method = 'users.list'
        return self._make_request(method, params)

    def user_id_to_name(self, user_id, get_realname=True, force_lookup=False):
        if force_lookup or not self.user_id_name_map:
            users = self.users_list()['members']
            self.user_id_name_map = {user['id']: {'name': user['name'], 'realname': user['profile']['real_name']} for
                                     user in users}
        if get_realname:
            return self.user_id_name_map.get(user_id)['realname']
        else:
            return self.user_id_name_map.get(user_id)['name']

    def user_name_to_id(self, user_name, force_lookup=False):
        if force_lookup or not self.user_id_name_map:
            users = self.users_list()['members']
            self.user_id_name_map = {user['id']: {'name': user['name'], 'realname': user['profile']['real_name']} for
                                     user in users}
        for id, names in self.user_id_name_map.iteritems():
            if names['name'] == user_name or names['realname'] == user_name:
                return id
        return None

    def chat_post_message(self, channel, text, **params):
        """chat.postMessage

        This method posts a message to a channel.

        https://api.slack.com/methods/chat.postMessage
        """
        method = 'chat.postMessage'
        params.update({
            'channel': channel,
            'text': text,
        })
        return self._make_request(method, params)

    def chat_update_message(self, channel, text, timestamp, **params):
        """chat.update

        This method updates a message.

        Required parameters:
            `channel`: Channel containing the message to be updated. (e.g: "C1234567890")
            `text`: New text for the message, using the default formatting rules. (e.g: "Hello world")
            `timestamp`:  Timestamp of the message to be updated (e.g: "1405894322.002768")

        https://api.slack.com/methods/chat.update
        """
        method = 'chat.update'
        if self._channel_is_name(channel):
            # chat.update only takes channel ids (not channel names)
            channel = self.channel_name_to_id(channel)
        params.update({
            'channel': channel,
            'text': text,
            'ts': timestamp,
        })
        return self._make_request(method, params)

    def file_upload(self, channels, file, **params):
        """files.upload
        
        This method uploads a file.
        
        Required parameters:
            `channels`: An array of the channels names to share the file
            `file`: The file path to upload
        
        https://api.slack.com/methods/files.upload   
        """
        method = 'files.upload'
        channel_ids = []
        for channel in channels:
            if self._channel_is_name(channel):
                # If the channel id is not found, will share the file as private by default 
                channel_ids.append(self.channel_name_to_id(channel))

        params.update({
            'channels': ','.join(channel_ids),
        })

        files = {'file': open(file, 'rb')}

        return self._make_request(method, params, files)


class SlackHandler(logging.Handler):
    """A logging handler that posts messages to a Slack channel!

    References:
    http://docs.python.org/2/library/logging.html#handler-objects
    """

    def __init__(self, token, channel, verify=False, **kwargs):
        super(SlackHandler, self).__init__()
        self.client = SlackClient(token, verify)
        self.channel = channel
        self._kwargs = kwargs

    def emit(self, record):
        message = self.format(record)
        self.client.chat_post_message(self.channel,
                                      message,
                                      **self._kwargs)
