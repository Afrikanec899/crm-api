import json
import re

from .utils import ERROR_IDENTIFIERS


class XCardError(Exception):
    """
    All errors specific to XCard api requests will be subclassed
    from XCardError which is subclassed from Exception.
    """

    pass


class XCardRequestError(XCardError):
    def __init__(self, message, request_context, http_status, body):
        self._message = message
        self._request_context = request_context
        self._http_status = http_status
        self._body = body
        self._api_error = {}
        self._api_call_status = None
        self._api_error_code = None
        self._api_error_message = None
        self._api_call_status = int(self._body['callstatus'])

        if 'errormessage' in self._body:
            self._api_error_message = self._body['errormessage']

        if 'errorIdentifier' in self._body:
            self._api_error['code'] = int(self._body['errorIdentifier'])
            error = ERROR_IDENTIFIERS.get(self._api_error['code'], {})
            self._api_error['message'] = error.get('message')
            self._api_error['description'] = error.get('description')

            self._api_error_code = self._api_error['code']

        # We do not want to print the file bytes
        request = self._request_context

        super(XCardRequestError, self).__init__(
            "\n\n"
            + "  Message: %s\n" % self._message
            + "  Method:  %s\n" % request.get('method')
            + "  Params:  %s\n" % request.get('params')
            + "\n"
            + "  HTTP Status:  %s\n" % self._http_status
            + "  Response:\n    %s" % re.sub(r"\n", "\n    ", json.dumps(self._body, indent=2))
            + "\n"
        )

    def request_context(self):
        return self._request_context

    def http_status(self):
        return self._http_status

    def body(self):
        return self._body

    def api_error_message(self):
        return self._api_error_message

    def api_error_code(self):
        return self._api_error_code

    def api_error(self):
        return self._api_error

    def api_call_status(self):
        return self._api_call_status

    def get_message(self):
        return self._message
