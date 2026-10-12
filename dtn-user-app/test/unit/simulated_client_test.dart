// DTN Messenger — Simulated Transport Unit Tests

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:dtn_messenger/core/models/message.dart';
import 'package:dtn_messenger/core/models/peer_node.dart';
import 'package:dtn_messenger/core/transport/simulated_dtn_client.dart';
import 'package:dtn_messenger/core/transport/dtn_client.dart';

void main() {
  late SimulatedDtnClient client;

  setUp(() {
    client = SimulatedDtnClient(deliveryDelayMs: 100, failureRate: 0.0);
  });

  tearDown(() async {
    await client.dispose();
  });

  // ── Basic properties ──────────────────────────────────────────────────────

  test('SimulatedDtnClient reports isSimulated = true', () {
    expect(client.isSimulated, isTrue);
  });

  test('Connection description mentions SIMULATION', () {
    expect(client.connectionDescription.toUpperCase(), contains('SIMULATION'));
  });

  // ── Peer discovery ─────────────────────────────────────────────────────────

  group('Peer discovery', () {
    test('Returns a non-empty list of simulated peers', () async {
      final result = await client.discoverPeers();
      expect(result.isOk, isTrue);
      expect(result.value, isNotNull);
      expect(result.value!.isNotEmpty, isTrue);
    });

    test('All returned peers are marked isSimulated', () async {
      final result = await client.discoverPeers();
      for (final peer in result.value!) {
        expect(
          peer.isSimulated,
          isTrue,
          reason: '${peer.nodeId} should be marked simulated',
        );
      }
    });

    test('Peers have distinct nodeIds', () async {
      final result = await client.discoverPeers();
      final ids = result.value!.map((p) => p.nodeId).toSet();
      expect(ids.length, equals(result.value!.length));
    });

    test('Includes a DTN reachable peer', () async {
      final result = await client.discoverPeers();
      expect(
        result.value!.any(
          (p) => p.reachability == PeerReachability.dtnReachable,
        ),
        isTrue,
      );
    });

    test('Includes a stale peer', () async {
      final result = await client.discoverPeers();
      expect(
        result.value!.any((p) => p.reachability == PeerReachability.stale),
        isTrue,
      );
    });
  });

  // ── Session management ─────────────────────────────────────────────────────

  group('Session management', () {
    test('requestSession succeeds for reachable peer', () async {
      final peers = (await client.discoverPeers()).value!;
      final peer = peers.firstWhere(
        (p) => p.reachability == PeerReachability.dtnReachable,
      );
      final result = await client.requestSession(peer);
      expect(result.isOk, isTrue);
    });

    test('requestSession fails for unreachable peer', () async {
      final peers = (await client.discoverPeers()).value!;
      final peer = peers.firstWhere(
        (p) => p.reachability == PeerReachability.unreachable,
      );
      final result = await client.requestSession(peer);
      expect(result.isOk, isFalse);
      expect(result.error, isNotNull);
    });

    test('closeSession completes without error', () async {
      final result = await client.closeSession('any-node');
      expect(result.isOk, isTrue);
    });
  });

  // ── Message submission & delivery events ────────────────────────────────────

  group('Message submission and delivery events', () {
    test('submitMessage returns ok', () async {
      final msg = Message.createText(
        conversationId: 'conv-sim',
        senderId: 'local',
        recipientId: 'sim-node-alpha',
        text: 'Test message',
      );
      final result = await client.submitMessage(msg);
      expect(result.isOk, isTrue);
    });

    test(
      'Delivery progresses to peerTransferred then destinationDelivered',
      () async {
        final client0 = SimulatedDtnClient(
          deliveryDelayMs: 50,
          failureRate: 0.0,
        );
        addTearDown(() async => await client0.dispose());

        final msg = Message.createText(
          conversationId: 'conv-delivery',
          senderId: 'local',
          recipientId: 'sim-node-alpha',
          text: 'Delivery test',
        );

        final events = <DeliveryEvent>[];
        final sub = client0.deliveryEvents.listen(events.add);

        await client0.submitMessage(msg);

        // Wait for both events with timeout.
        await Future.delayed(const Duration(milliseconds: 400));
        await sub.cancel();

        expect(events.length, greaterThanOrEqualTo(1));
        expect(
          events.any((e) => e.newStatus == DeliveryStatus.peerTransferred),
          isTrue,
        );
      },
    );

    test('Delivery event contains correct messageId', () async {
      final client0 = SimulatedDtnClient(deliveryDelayMs: 50, failureRate: 0.0);
      addTearDown(() async => await client0.dispose());

      final msg = Message.createText(
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        text: 'hi',
      );

      final completer = Completer<DeliveryEvent>();
      client0.deliveryEvents.listen((e) {
        if (!completer.isCompleted) completer.complete(e);
      });

      await client0.submitMessage(msg);
      final event = await completer.future.timeout(
        const Duration(milliseconds: 500),
      );
      expect(event.messageId, equals(msg.messageId));
    });

    test('Peer transfer is not the same as destination delivered', () async {
      expect(
        DeliveryStatus.peerTransferred,
        isNot(equals(DeliveryStatus.destinationDelivered)),
      );
    });
  });

  // ── Receive messages ────────────────────────────────────────────────────────

  test('receiveMessages returns ok with empty list in simulation', () async {
    final result = await client.receiveMessages();
    expect(result.isOk, isTrue);
    expect(result.value, isA<List>());
  });

  // ── Diagnostics ─────────────────────────────────────────────────────────────

  test('getDiagnostics includes mode=SIMULATION', () async {
    final diags = await client.getDiagnostics();
    expect(diags['mode'], equals('SIMULATION'));
  });

  test('getDiagnostics includes missing_integration key', () async {
    final diags = await client.getDiagnostics();
    expect(diags.containsKey('missing_integration'), isTrue);
  });
}
