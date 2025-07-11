from datetime import datetime
from http.client import OK
from typing import Any, Dict
from urllib import parse
from uuid import uuid4

import urllib3

from XCardAPI.exceptions import XCardRequestError

__all__ = ['XCardAPI', 'XCardResponse']


class XCardResponse:
    """Encapsulates an http response from XCard's API."""

    def __init__(self, data=None, http_status=None, call=None):
        """Initializes the object's internal data.
        Args:
            data (optional): The response body as raw string.
            http_status (optional): The http status code.
            call (optional): The original call that was made.
        """
        self._raw_data = data

        self._data = self.get_data()
        if self._data:
            self._prepare_additional_data()

        self._http_status = http_status
        self._call = call

    def _prepare_additional_data(self):
        self._call_id = self._data.pop('callid', None)
        self._call_method = self._data.pop('methodname', None)
        self._call_execution_time = self._data.pop('callexecutiontime', None)
        if self._call_execution_time is not None:
            self._call_execution_time = datetime.fromisoformat(self._call_execution_time.replace('Z', '+00:00'))
        self._call_is_cached = bool(int(self._data.pop('isresultcached', '0')))
        # For is_success check
        self._call_status = int(self._data.pop('callstatus', '0'))
        self._error_code = self._data.pop('errorIdentifier', None)
        if self._error_code is not None and self._error_code.isdigit():
            self._error_code = int(self._error_code)
        self._error_message = self._data.pop('errormessage', None)

    def get_data(self):
        """Returns the response data."""
        try:
            return dict(parse.parse_qsl(self._raw_data.decode('utf-8')))
        except (TypeError, ValueError):
            return self._raw_data

    def http_status(self):
        """Returns the http status code of the response."""
        return self._http_status

    def is_cached(self):
        return self._call_is_cached

    def call_execution_time(self):
        return self._call_execution_time

    def call_status(self):
        return self._call_status

    def call_method(self):
        return self._call_method

    def call_id(self):
        return self._call_id

    def data(self):
        return self._data

    def is_success(self):
        """Returns boolean indicating if the call was successful."""
        if not self._data or self._call_status == 0 or self._error_code is not None or self._error_message is not None:
            # Is a dictionary, has error in it
            return False

        elif self._http_status == OK:
            # HTTP Okay
            return True
        else:
            # Something else
            return False

    def is_failure(self):
        """Returns boolean indicating if the call failed."""
        return not self.is_success()

    def error(self):
        """
        Returns a XCardRequestError (located in the exceptions module) with
        an appropriate debug message.
        """
        if self.is_failure():
            return XCardRequestError("Call was not successful", self._call, self.http_status(), self.get_data())
        else:
            return None


class XCardAPI:
    """
    The following API calls have been enabled for you:

    echotest,
    accountbalanceinquiry,
    balanceinquiry,
    createvirtualcard,
    getcardstatus,
    setcardstatus,
    getvirtualcarddetails,
    getvirtualcardpan,
    cardstatement,
    modifycardholderdetails,
    payout,
    verifycvx2
    unload,
    load,
    """

    def __init__(
        self,
        login: str,
        password: str,
        partner_id: str,
        ca_certs: str,
        cert_file: str,
        key_file: str,
        key_password: str,
        is_dev: bool = True,
    ) -> None:

        self.default_request_params = {'login': login, 'password': password, 'partnerid': partner_id}

        self.http = urllib3.PoolManager(
            cert_file=cert_file,
            key_file=key_file,
            key_password=key_password,
            ca_certs=ca_certs,
            cert_reqs='CERT_REQUIRED',
        )

        self.last_callid = None
        self.is_dev = is_dev
        self.api_url = 'https://sandbox.cardstatus.com' if self.is_dev else 'https://api.cardstatus.com'

    def _generate_callid(self) -> str:
        return f'{datetime.strftime(datetime.now(), "%Y%m%d")}-{uuid4()}'

    def _process_response(self, response) -> Dict[str, Any]:
        data = response.data.decode('utf-8')
        return dict(parse.parse_qsl(data))

    def _construct_request_params(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        fields = self.default_request_params
        if params:
            fields.update(params)
        self.last_callid = self._generate_callid()
        fields['callid'] = self.last_callid
        fields['methodname'] = method

        return fields

    def _request(self, method: str, params: Dict[str, Any] = None) -> XCardResponse:
        fields = self._construct_request_params(method=method, params=params)
        request = self.http.request('POST', self.api_url, fields=fields)
        response = XCardResponse(
            data=request.data, http_status=request.status, call={'method': method, 'params': params},
        )

        if response.is_failure():
            raise response.error()

        return response

    def echo(self, textin: str) -> XCardResponse:
        """
        echotest

        The echotest method is always available. It accepts a UTF-8 encoded string, and returns the same string
        you provided on its output. It is intended to test connectivity to the server,
        authentication credentials and character encoding handling.
        """
        params = {'textin': textin}
        data = self._request('echotest', params=params)
        return data

    def get_account_balance(self) -> XCardResponse:
        """
        accountbalanceinquiry

        Returns the current partner funding account balance. Please note that for funding accounts that have
        a minimum balance requirement, the available funds may not match the current account balance.
        Only available funds can be used to load cards.
        """

        data = self._request('accountbalanceinquiry')
        return data

    def get_card_balance(self, card_id: int) -> XCardResponse:
        """
        balanceinquiry

        Note: this call should be used ONLY as a fall-back to a failure to query locally
        stored balance data obtained via Method: getrecentcardactivity (NA)

        Returns the current balance of the card. There are three balances for every card.
        The financial balance shows the actual balance on the card. The blocked balance represents all
        transactions from merchants which have been accepted but not yet finalised -
        these funds are still on the card account, but are being held pending the claiming of the funds by
        the merchant or reversal of the authorisation in which case the funds are un-blocked.
        The available balance is the financial balance minus the blocked balance,
        which is used when determining the funds available for purchase or unloading from the card.
        """

        params = {'cardid': card_id}
        data = self._request('balanceinquiry', params=params)
        return data

    def get_card_status(self, card_id: int) -> XCardResponse:
        """
        getcardstatus
        
        ORDERED   The card has been sent for embossing (physical only)
        SHIPPED   The card was shipped by the fulfilment house (physical only)
        PURCHASED The card was purchased at a retail shop (physical only)
        ACTIVE    The card is active and ready to use
        SUSPENDED The card is suspended from use, no transactions will be authorised
        LOST      The card has been reported lost (end state)
        STOLEN    The card has been reported stolen (end state)
        CANCELLED The card has been cancelled (end state)
        EXPIRED   The card is expired (end state)

        Note: this call should be used ONLY as a fall-back to a failure to query
        locally stored balance data obtained via Method: getrecentsystemevents(NA)

        Retrieve a card’s current status.
        """

        params = {'cardid': card_id}
        data = self._request('getcardstatus', params=params)
        return data

    def set_card_status(self, card_id: int, status: str) -> XCardResponse:
        """
        setcardstatus

        ACTIVE     Possible if a card is in the ORDERED, SHIPPED, PURCHASED, or SUSPENDED states.
        SUSPENDED  Possible if a card is in the ACTIVE state.
        LOST       Possible if a card is in the ACTIVE, SUSPENDED, ORDERED, SHIPPED or PURCHASED states.
        STOLEN     Possible if a card is in the ACTIVE, SUSPENDED, ORDERED, SHIPPED or PURCHASED states.
        CANCELLED  Possible if a card is in the ACTIVE, SUSPENDED, ORDERED, SHIPPED or PURCHASED states.

        Change a card’s status.
        """

        params = {'cardid': card_id, 'status': status}
        data = self._request('setcardstatus', params=params)
        return data

    def verify_cvx2(self, card_id: int, cvx2: str) -> XCardResponse:
        """
        verifycvx2
        
        Verify a card’s 3-digit CVC2/CVV2 number. This can be used as part of a card activation process to
        determine if the customer received the card before it is activated.
        """

        params = {'cardid': card_id, 'verifycvx2': cvx2}
        data = self._request('verifycvx2', params=params)
        return data

    def get_virtual_card_details(self, card_id: int) -> XCardResponse:
        """
        getvirtualcarddetails

        Return the CVX2 and expiration date of a virtual card.
        """

        params = {'cardid': card_id}
        data = self._request('getvirtualcarddetails', params=params)
        return data

    def get_virtual_card_pan(self, card_id: int) -> XCardResponse:
        """
        getvirtualcardpan

        Return the PAN of the virtual card as an image. The image is returned as a base64 encoded PNG.
        """

        params = {'cardid': card_id}
        data = self._request('getvirtualcardpan', params=params)
        return data

    def get_card_statement(self, card_id: int, begin_date: datetime.date, end_date: datetime.date) -> XCardResponse:
        """
        cardstatement

        Note: It is strongly receommended that the implementer consider using Method: getrecentcardactivity(NA)
        to obtain substantially richer transaction data than provided by this call and querying for the data locally.

        The card statement call returns CSV formatted data which is base64 encoded.
        The CSV file includes a header row that should be used to match the columns.
        While the order of the columns is not expected to change, additional columns will be added over time,
        and the implementer should consider this.
        """

        params = {'cardid': card_id, 'begindate': begin_date.isoformat(), 'enddate': end_date.isoformat()}
        data = self._request('cardstatement', params=params)
        return data

    def modify_cardholder_details(
        self,
        card_id: int,
        first_name: str,
        last_name: str,
        gender: str,
        date_of_birth: datetime.date,
        address1: str,
        city: str,
        post_code: str,
        country_code: str,
        mobile_country: int,
        mobile_number: int,
        email: str,
        language: str,
        address2: str = None,
        state: str = None,
    ) -> XCardResponse:
        """
        modifycardholderdetails

        Updates the records of the associated user. Only the specific parameters which are passed will be modified,
        all other parameters will remain unchanged.
        """

        params = {
            'cardid': card_id,
            'firstname': first_name,
            'lastname': last_name,
            'gender': gender,
            'dateofbirth': date_of_birth.isoformat(),
            'addressline1': address1,
            'addressline2': address2,
            'language': language,
            'city': city,
            'state': state,
            'postcode': post_code,
            'country': country_code,
            'mobilecountry': mobile_country,
            'mobilenumber': mobile_number,
            'email': email,
        }
        data = self._request('modifycardholderdetails', params=params)
        return data

    def create_virtual_card(
        self,
        product_id: str,
        currency: str,
        external_id: str,
        first_name: str,
        last_name: str,
        gender: str,
        date_of_birth: datetime.date,
        address1: str,
        city: str,
        post_code: str,
        country_code: str,
        mobile_country: int,
        mobile_number: int,
        email: str,
        card_type: str = None,
        name_on_card: str = None,
        address2: str = None,
        address3: str = None,
        state: str = None,
    ) -> XCardResponse:
        """
        createvirtualcard

        Create a virtual card and return the card identifier, CVC2/CVV2 number and expiration date.
        The card PAN must be requested separately.
        """
        params = {
            'productid': product_id,
            'currency': currency,
            'externalid': external_id,
            'firstname': first_name,
            'lastname': last_name,
            'gender': gender,
            'dateofbirth': date_of_birth.isoformat(),
            'addressline1': address1,
            # 'addressline2': address2,
            # 'addressline3': address3,
            'city': city,
            'postcode': post_code,
            'country': country_code,
            'mobilecountry': mobile_country,
            'mobilenumber': mobile_number,
            'email': email,
        }
        if card_type is not None:
            params['cardtype'] = card_type

        if name_on_card is not None:
            params['nameoncard'] = name_on_card

        if state is not None:
            params['state'] = state

        if address2 is not None:
            params['addressline2'] = address2

        if address3 is not None:
            params['addressline3'] = address3

        data = self._request('createvirtualcard', params=params)
        return data

    def payout(
        self,
        card_id,
        amount,
        currency,
        payment_method,
        description,
        transaction_reference,
        recipient_first_name,
        recipient_last_name,
        iban,
        bic=None,
    ) -> XCardResponse:
        """
        payout

        Send funds from a card to an external bank account. All fields except BIC are mandatory.
        """

        params = {
            'cardid': card_id,
            'amount': amount,
            'currency': currency,
            'paymentmethod': payment_method,
            'description': description,
            'transactionreference': transaction_reference,
            'beneficiaryfirstname': recipient_first_name,
            'beneficiarylastname': recipient_last_name,
            'beneficiaryiban': iban,
        }
        if bic is not None:
            params['beneficiarybic'] = bic

        data = self._request('payout', params=params)
        return data

    def load(
        self, card_id, amount, currency, description, transaction_reference, source: str = None,
    ) -> XCardResponse:
        """
        load

        The load method transfers the given amount from the client’s funding account to the card in question.
        If the money is not available on the client’s funding account the load will be declined.
        Please note that the call will be considered complete even if the load is declined,
        so it is important to always check the output values of this method.
        """

        params = {
            'cardid': card_id,
            'amount': amount,
            'currency': currency,
            'description': description,
            'transactionreference': transaction_reference,
        }
        if source is not None:
            params['source'] = source

        data = self._request('load', params=params)
        return data

    def unload(
        self, card_id, amount, currency, description, transaction_reference, destination: str = None,
    ) -> XCardResponse:
        """
        unload

        Unload an amount from the card. If the amount to unload is greater than the balance on the card,
        the unload will be declined. Unloads are allowed in any card state.
        The call itself will be considered completed even if the unload is declined,
        so you must always check the return values to see if the actual amount was unloaded.
        """

        params = {
            'cardid': card_id,
            'amount': amount,
            'currency': currency,
            'description': description,
            'transactionreference': transaction_reference,
        }
        if destination is not None:
            params['destination'] = destination

        data = self._request('unload', params=params)
        return data
