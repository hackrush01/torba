import six
from binascii import hexlify
from twisted.trial import unittest
from twisted.internet import defer

from torba.coin.bitcoinsegwit import MainNetLedger

from .test_transaction import get_transaction, get_output

if six.PY3:
    buffer = memoryview


class MockNetwork:

    def __init__(self, history, transaction):
        self.history = history
        self.transaction = transaction
        self.address = None
        self.get_history_called = []
        self.get_transaction_called = []

    def get_history(self, address):
        self.get_history_called.append(address)
        self.address = address
        return defer.succeed(self.history)

    def get_merkle(self, txid, height):
        return {'merkle': ['abcd01'], 'pos': 1}

    def get_transaction(self, tx_hash):
        self.get_transaction_called.append(tx_hash)
        return defer.succeed(self.transaction[tx_hash.decode()])


class MockHeaders:
    def __init__(self, ledger):
        self.ledger = ledger
        self.height = 1

    def __len__(self):
        return self.height

    def __getitem__(self, height):
        return {'merkle_root': 'abcd04'}


class TestSynchronization(unittest.TestCase):

    def setUp(self):
        self.ledger = MainNetLedger(db=MainNetLedger.database_class(':memory:'), headers_class=MockHeaders)
        return self.ledger.db.start()

    @defer.inlineCallbacks
    def test_update_history(self):
        account = self.ledger.account_class.generate(self.ledger, u"torba")
        address = yield account.receiving.get_or_create_usable_address()
        address_details = yield self.ledger.db.get_address(address)
        self.assertEqual(address_details['history'], None)

        self.ledger.headers.height = 3
        self.ledger.network = MockNetwork([
            {'tx_hash': b'abcd01', 'height': 1},
            {'tx_hash': b'abcd02', 'height': 2},
            {'tx_hash': b'abcd03', 'height': 3},
        ], {
            'abcd01': hexlify(get_transaction(get_output(1)).raw),
            'abcd02': hexlify(get_transaction(get_output(2)).raw),
            'abcd03': hexlify(get_transaction(get_output(3)).raw),
        })
        yield self.ledger.update_history(address)
        self.assertEqual(self.ledger.network.get_history_called, [address])
        self.assertEqual(self.ledger.network.get_transaction_called, [b'abcd01', b'abcd02', b'abcd03'])

        address_details = yield self.ledger.db.get_address(address)
        self.assertEqual(address_details['history'], 'abcd01:1:abcd02:2:abcd03:3:')

        self.ledger.network.get_history_called = []
        self.ledger.network.get_transaction_called = []
        yield self.ledger.update_history(address)
        self.assertEqual(self.ledger.network.get_history_called, [address])
        self.assertEqual(self.ledger.network.get_transaction_called, [])

        self.ledger.network.history.append({'tx_hash': b'abcd04', 'height': 4})
        self.ledger.network.transaction['abcd04'] = hexlify(get_transaction(get_output(4)).raw)
        self.ledger.network.get_history_called = []
        self.ledger.network.get_transaction_called = []
        yield self.ledger.update_history(address)
        self.assertEqual(self.ledger.network.get_history_called, [address])
        self.assertEqual(self.ledger.network.get_transaction_called, [b'abcd04'])
        address_details = yield self.ledger.db.get_address(address)
        self.assertEqual(address_details['history'], 'abcd01:1:abcd02:2:abcd03:3:abcd04:4:')
