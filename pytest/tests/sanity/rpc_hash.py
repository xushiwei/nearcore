#!/usr/bin/env python3
"""Test computing block hash from data provided by JSON RPCs."""

import hashlib
import json
import pathlib
import sys
import typing
import unittest

import base58

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2] / 'lib'))

from configured_logger import logger
import cluster
import utils
import serializer

import messages
import messages.crypto
import messages.block


def serialize(msg: typing.Any) -> bytes:
    return serializer.BinarySerializer(messages.schema).serialize(msg)


def compute_block_hash(header: typing.Dict[str, typing.Any],
                       msg_version: int) -> str:
    """Computes block hash based on given block header.

    Args:
        header: JSON representation of the block header.
        msg_version: Version of the BlockHeaderInnerRest to use when serialising
            and computing hash.  This depends on protocol version used when the
            block was generated.
    Returns:
        Base58-encoded block hash.
    """

    def get_int(key: str) -> typing.Optional[int]:
        value = header.get(key)
        if value is None:
            return None
        return int(value)

    def get_hash(key: str) -> bytes:
        value = header[key]
        result = base58.b58decode(value)
        assert len(result) == 32, (key, value, len(result))
        return result

    def encode_bitmap(vec: typing.Sequence[bool]) -> bytes:
        bases = tuple(2**n for n in range(8))
        return bytes(
            sum(is_set * base
                for is_set, base in zip(vec[n:n + 8], bases))
            for n in range(0, len(vec), 8))

    def sha256(*chunks: bytes) -> bytes:
        return hashlib.sha256(b''.join(chunks)).digest()

    prev_hash = get_hash('prev_hash')

    inner_lite = messages.block.BlockHeaderInnerLite()
    inner_lite.height = get_int('height')
    inner_lite.epoch_id = get_hash('epoch_id')
    inner_lite.next_epoch_id = get_hash('next_epoch_id')
    inner_lite.prev_state_root = get_hash('prev_state_root')
    inner_lite.outcome_root = get_hash('outcome_root')
    inner_lite.timestamp = get_int('timestamp_nanosec')
    inner_lite.next_bp_hash = get_hash('next_bp_hash')
    inner_lite.block_merkle_root = get_hash('block_merkle_root')
    inner_lite_blob = serialize(inner_lite)
    inner_lite_hash = sha256(inner_lite_blob)

    inner_rest_msg = {
        1: messages.block.BlockHeaderInnerRest,
        2: messages.block.BlockHeaderInnerRestV2,
        3: messages.block.BlockHeaderInnerRestV3
    }[msg_version]

    inner_rest = inner_rest_msg()
    # Some of the fields are superfluous in some of the versions of the message
    # but that’s quite all right.  Serialiser will ignore them and
    # unconditionally setting them makes the code simpler.
    inner_rest.chunk_receipts_root = get_hash('chunk_receipts_root')
    inner_rest.chunk_headers_root = get_hash('chunk_headers_root')
    inner_rest.chunk_tx_root = get_hash('chunk_tx_root')
    inner_rest.chunks_included = get_int('chunks_included')
    inner_rest.challenges_root = get_hash('challenges_root')
    inner_rest.random_value = get_hash('random_value')
    # TODO: Handle non-empty list.
    inner_rest.validator_proposals = header['validator_proposals']
    inner_rest.chunk_mask = encode_bitmap(header['chunk_mask'])
    inner_rest.gas_price = get_int('gas_price')
    inner_rest.total_supply = get_int('total_supply')
    # TODO: Handle non-empty list.
    inner_rest.challenges_result = header['challenges_result']
    inner_rest.last_final_block = get_hash('last_final_block')
    inner_rest.last_ds_final_block = get_hash('last_ds_final_block')
    inner_rest.block_ordinal = get_int('block_ordinal')
    inner_rest.prev_height = get_int('prev_height')
    # TODO: Handle non-None values.
    inner_rest.epoch_sync_data_hash = header['epoch_sync_data_hash']
    inner_rest.approvals = [
        messages.crypto.Signature(approval) for approval in header['approvals']
    ]
    inner_rest.latest_protocol_version = get_int('latest_protocol_version')
    inner_rest_blob = serialize(inner_rest)
    inner_rest_hash = sha256(inner_rest_blob)

    inner_hash = sha256(inner_lite_hash + inner_rest_hash)
    block_hash = sha256(inner_hash + prev_hash)

    return base58.b58encode(block_hash).decode('ascii')


class HashTestCase(unittest.TestCase):
    _nodes: typing.Sequence[cluster.BaseNode]

    def __init__(self, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self._nodes = ()
        self.maxDiff = None

    def test_compute_block_hash(self):
        """Tests that compute_block_hash function works correctly.

        This is a sanity check for cases when someone modifies the test code
        itself.  If this test breaks than all the other tests will break as
        well.  This test runs the compute_block_hash function on a well-known
        static input checking expected hash.
        """
        header = {
            'height':
                4,
            'prev_height':
                3,
            'epoch_id':
                '11111111111111111111111111111111',
            'next_epoch_id':
                'AuatKw3hiGmXed3uT2u4Die6ZRGZhEHn34kTyVpGnYLM',
            'prev_hash':
                'BUcVEkMq3DcZzDGgeh1sb7FFuD86XYcXpEt25Cf34LuP',
            'prev_state_root':
                'Bn786g4GdJJigSP4qRSaVCfeMotWVX88cV1LTZhD6o3z',
            'chunk_receipts_root':
                '9ETNjrt6MkwTgSVMMbpukfxRshSD1avBUUa4R4NuqwHv',
            'chunk_headers_root':
                'Fk7jeakmi8eruvv4L4ToKs7MV1YG64ETZtASQYjGBWK1',
            'chunk_tx_root':
                '7tkzFg8RHBmMw1ncRJZCCZAizgq4rwCftTKYLce8RU8t',
            'outcome_root':
                '7tkzFg8RHBmMw1ncRJZCCZAizgq4rwCftTKYLce8RU8t',
            'chunks_included':
                1,
            'challenges_root':
                '11111111111111111111111111111111',
            'timestamp':
                1642022757141096960,
            'timestamp_nanosec':
                '1642022757141096960',
            'random_value':
                'GxYrjCxQtfG2K7hX6w4aPs3usTskzfCkbVc2icSQMF7h',
            'validator_proposals': [],
            'chunk_mask': [True],
            'gas_price':
                '1000000000',
            'block_ordinal':
                4,
            'rent_paid':
                '0',
            'validator_reward':
                '0',
            'total_supply':
                '3000000000000000000000000000000000',
            'challenges_result': [],
            'last_final_block':
                'GTudmqKJQjEVCrdi31vcHqXoEpvEScmZ9BhBf3gPJ4pp',
            'last_ds_final_block':
                'BUcVEkMq3DcZzDGgeh1sb7FFuD86XYcXpEt25Cf34LuP',
            'next_bp_hash':
                '236RGxQc2xSqukyiBkixtZSqKu679ZxeS6vP8zzAL9vW',
            'block_merkle_root':
                'Gf3uWgULzc5WDuaAq4feehh7M1TFRFxTWVv2xH6AsnpA',
            'epoch_sync_data_hash':
                None,
            'approvals': [
                'ed25519:5Jdeg8rk5hAbcooyxXQSTcxBgUK39Z8Qtfkhqmpi26biU26md5wBiFvkAEGXrMyn3sgq3cTMG8Lr3HD7RxWPjkPh',
                'ed25519:4vqTaN6bucu6ALsb1m15e8HWGGxLQeKJhWrcU8zPRrzfkZbakaSzW8rfas2ZG89rFKheZUyrnZRKooRny6YKFyKi'
            ],
            'signature':
                'ed25519:5mGi9dyuyt7TnSpPFjbEWSJThDdiEV9NNQB11knXvRbxSv8XfBT5tdVVFypeqpZjeB3fD7qgJpWhTj3KvdGbcXdu',
            'latest_protocol_version':
                50
        }
        for msg_ver, block_hash in (
            (1, '3ckGjcedZiN3RnvfiuEN83BtudDTVa9Pub4yZ8R737qt'),
            (2, 'Hezx56VTH815G6JTzWqJ7iuWxdR9X4ZqGwteaDF8q2z'),
            (3, '82v8RAc66tWpdjRCsoSrgnzpU6JMhpjbWKmUEcfkzX6T'),
        ):
            self.assertEqual(block_hash, compute_block_hash(header, msg_ver))

    def _test_block_hash(self,
                         msg_version: int,
                         protocol_version: typing.Optional[int] = None) -> None:
        """Starts a cluster, fetches a block and computes its hash.

        Args:
            msg_version: Version of the BlockHeaderInnerRest to use when
                serialising and computing hash.
            protocol_version: If given, protocol version to use in the cluster
                (which will be set in genesis); If not given, cluster will be
                started with the newest supported protocol version.
        """
        genesis_overrides = []
        if protocol_version:
            genesis_overrides = [['protocol_version', protocol_version]]

        nodes = ()
        try:
            nodes = cluster.start_cluster(2, 0, 1, None, genesis_overrides, {})
            node = nodes[0]
            block_id = utils.wait_for_blocks(node, target=1)
            header = node.get_block(block_id.hash)['result']['header']
        finally:
            for node in nodes:
                node.cleanup()

        self.assertEqual((block_id.height, block_id.hash),
                         (header['height'], header['hash']), (block_id, header))

        got = compute_block_hash(header, msg_version)
        self.assertEqual(header['hash'], got)

    def test_block_hash_v1(self):
        """Starts a cluster, fetches a block and computes its hash.

        The cluster is started with a protocol version in which the first
        version of the BlockHeaderInnerRest has been used.
        """
        self._test_block_hash(1, 24)

    def test_block_hash_v2(self):
        """Starts a cluster, fetches a block and computes its hash.

        The cluster is started with a protocol version in which the second
        version of the BlockHeaderInnerRest has been used.
        """
        self._test_block_hash(2, 42)

    def test_block_hash_v3(self):
        """Starts a cluster, fetches a block and computes its hash.

        The cluster is started with a protocol version in which the third
        version of the BlockHeaderInnerRest has been used.
        """
        self._test_block_hash(3, 50)

    def test_block_hash_latest(self):
        """Starts a cluster, fetches a block and computes its hash.

        The cluster is started with the newest protocol version supported by the
        node.  If this test fails while others pass this may indicate that a new
        BlockHeaderInnerRest message has been introduced and this test needs to
        be updated to support it.
        """
        self._test_block_hash(3)


if __name__ == '__main__':
    unittest.main()
