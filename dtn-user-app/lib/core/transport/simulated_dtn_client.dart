// DTN Messenger — Simulated DTN Client
// ─────────────────────────────────────────────────────────────────────────────
// THIS IS A DETERMINISTIC DEVELOPMENT/SIMULATION ADAPTER.
// It does NOT communicate with any real hardware or network endpoint.
// All peers and delivery events are synthetic.
//
// Purpose:
//   Allow the full UI/UX, persistence, and message-flow logic to be developed
//   and tested without a physical ESP8266 node or real DTN backend.
//
// Missing backend contract (documented for integration):
//   A real DtnClient implementation needs these endpoints on the DTN gateway:
//   POST   /api/v1/message/submit        → accept an outgoing bundle
//   GET    /api/v1/message/receive       → poll inbound bundles for this node
//   GET    /api/v1/message/{id}/status   → query delivery state of an outgoing msg
//   GET    /api/v1/peers                 → list currently visible/reachable peers
//   POST   /api/v1/session/request       → initiate DTN handshake with a peer
//   DELETE /api/v1/session/{nodeId}      → close a session
//   WebSocket /api/v1/events             → push delivery events (preferred)
// ─────────────────────────────────────────────────────────────────────────────

import 'dart:async';
import 'dart:math';

import '../models/message.dart';
import '../models/peer_node.dart';
import 'dtn_client.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Deterministic simulation peers
// ─────────────────────────────────────────────────────────────────────────────

List<PeerNode> _buildSimPeers() {
  final now = DateTime.now().toUtc().millisecondsSinceEpoch;
  return [
    PeerNode(
      nodeId: 'sim-node-alpha',
      displayName: '📡 Alpha Node [SIM]',
      address: '192.168.0.101',
      port: 8765,
      discoveryMethod: DiscoveryMethod.simulation,
      reachability: PeerReachability.dtnReachable,
      lastSeenMs: now - 30000,
      isSimulated: true,
    ),
    PeerNode(
      nodeId: 'sim-node-beta',
      displayName: '📡 Beta Node [SIM]',
      address: '192.168.0.102',
      port: 8765,
      discoveryMethod: DiscoveryMethod.simulation,
      reachability: PeerReachability.connected,
      lastSeenMs: now - 120000,
      isSimulated: true,
    ),
    PeerNode(
      nodeId: 'sim-node-gamma',
      displayName: '📡 Gamma Node [SIM]',
      address: '192.168.0.103',
      port: 8765,
      discoveryMethod: DiscoveryMethod.simulation,
      reachability: PeerReachability.discovered,
      lastSeenMs: now - 300000,
      isSimulated: true,
    ),
    PeerNode(
      nodeId: 'sim-node-delta',
      displayName: '📡 Delta Node [SIM] — Stale',
      address: '192.168.0.104',
      port: 8765,
      discoveryMethod: DiscoveryMethod.simulation,
      reachability: PeerReachability.stale,
      lastSeenMs: now - 12 * 60 * 1000,
      isSimulated: true,
    ),
    PeerNode(
      nodeId: 'sim-node-epsilon',
      displayName: '📡 Epsilon Node [SIM]',
      address: '192.168.0.105',
      port: 8765,
      discoveryMethod: DiscoveryMethod.simulation,
      reachability: PeerReachability.unreachable,
      lastSeenMs: now - 8 * 60 * 1000,
      lastError: 'Simulated connection timeout',
      isSimulated: true,
    ),
  ];
}

// ─────────────────────────────────────────────────────────────────────────────
// SimulatedDtnClient
// ─────────────────────────────────────────────────────────────────────────────

class SimulatedDtnClient implements DtnClient {
  SimulatedDtnClient({this.deliveryDelayMs = 4000, this.failureRate = 0.1});

  /// Simulated peer-transfer delay in milliseconds.
  final int deliveryDelayMs;

  /// Probability [0–1] that a message transfer fails in simulation.
  final double failureRate;

  final _eventController = StreamController<DeliveryEvent>.broadcast();
  final _rng = Random();

  final List<PeerNode> _peers = _buildSimPeers();
  final Map<String, String> _activeSessions = {}; // nodeId → status

  @override
  bool get isSimulated => true;

  @override
  String get connectionDescription =>
      '⚠️ SIMULATION MODE — No real DTN endpoint connected. '
      'All peers and delivery events are synthetic.';

  // ── Discovery ─────────────────────────────────────────────────────────────

  @override
  Future<TransportResult<List<PeerNode>>> discoverPeers() async {
    // Simulate network scan latency.
    await Future.delayed(const Duration(milliseconds: 800));
    // Randomise last-seen slightly for realism.
    final now = DateTime.now().toUtc().millisecondsSinceEpoch;
    final updated = _peers.map((p) {
      if (p.reachability == PeerReachability.dtnReachable ||
          p.reachability == PeerReachability.connected) {
        return p.copyWith(lastSeenMs: now - _rng.nextInt(60000));
      }
      return p;
    }).toList();
    return TransportResult.ok(updated);
  }

  // ── Session ───────────────────────────────────────────────────────────────

  @override
  Future<TransportResult<void>> requestSession(PeerNode peer) async {
    await Future.delayed(const Duration(milliseconds: 600));
    if (peer.reachability == PeerReachability.unreachable) {
      return const TransportResult.err(
        'Simulated connection refused: peer is marked unreachable.',
      );
    }
    _activeSessions[peer.nodeId] = 'connected';
    return const TransportResult.ok(null);
  }

  @override
  Future<TransportResult<void>> closeSession(String nodeId) async {
    _activeSessions.remove(nodeId);
    return const TransportResult.ok(null);
  }

  // ── Messaging ─────────────────────────────────────────────────────────────

  @override
  Future<TransportResult<void>> submitMessage(Message message) async {
    await Future.delayed(const Duration(milliseconds: 200));
    // Schedule simulated delivery events asynchronously.
    _scheduleSimulatedDelivery(message);
    return const TransportResult.ok(null);
  }

  void _scheduleSimulatedDelivery(Message message) {
    // Phase 1: Peer transfer after deliveryDelayMs.
    Future.delayed(Duration(milliseconds: deliveryDelayMs), () {
      if (_eventController.isClosed) return;
      if (_rng.nextDouble() < failureRate) {
        _eventController.add(
          DeliveryEvent(
            messageId: message.messageId,
            newStatus: DeliveryStatus.failed,
            failureReason:
                'Simulated transfer failure: no available relay in range.',
          ),
        );
        return;
      }
      _eventController.add(
        DeliveryEvent(
          messageId: message.messageId,
          newStatus: DeliveryStatus.peerTransferred,
          relayPath: [message.senderId, 'sim-relay-01'],
        ),
      );

      // Phase 2: Destination delivery after an additional delay.
      Future.delayed(Duration(milliseconds: deliveryDelayMs * 2), () {
        if (_eventController.isClosed) return;
        if (_rng.nextDouble() < failureRate / 2) {
          // Occasional final-hop failure.
          _eventController.add(
            DeliveryEvent(
              messageId: message.messageId,
              newStatus: DeliveryStatus.failed,
              failureReason: 'Simulated: destination node unreachable.',
            ),
          );
          return;
        }
        _eventController.add(
          DeliveryEvent(
            messageId: message.messageId,
            newStatus: DeliveryStatus.destinationDelivered,
            relayPath: [message.senderId, 'sim-relay-01', message.recipientId],
          ),
        );
      });
    });
  }

  @override
  Future<TransportResult<List<Message>>> receiveMessages() async {
    // Simulation returns no inbound messages unless explicitly injected.
    await Future.delayed(const Duration(milliseconds: 300));
    return const TransportResult.ok([]);
  }

  @override
  Future<TransportResult<DeliveryEvent>> queryMessageStatus(
    String messageId,
  ) async {
    // In simulation, we don't track status separately — events are pushed.
    return TransportResult.err(
      'Status polling not supported in simulation mode. '
      'Listen to deliveryEvents stream instead.',
    );
  }

  // ── Events ────────────────────────────────────────────────────────────────

  @override
  Stream<DeliveryEvent> get deliveryEvents => _eventController.stream;

  // ── Diagnostics ───────────────────────────────────────────────────────────

  @override
  Future<Map<String, dynamic>> getDiagnostics() async => {
    'mode': 'SIMULATION',
    'peers_discovered': _peers.length,
    'active_sessions': _activeSessions.length,
    'backend_endpoint': null,
    'warning':
        'This is a development simulation. '
        'No real DTN messages are transmitted.',
    'missing_integration': {
      'gateway_http_api': 'Not implemented — see transport/dtn_client.dart',
      'real_peer_discovery':
          'Wi-Fi LAN mDNS or UDP broadcast — not yet configured',
      'physical_radio': 'ESP8266 + NRF24L01+/ESP-NOW — hardware pending',
    },
  };

  @override
  Future<void> dispose() async {
    await _eventController.close();
  }
}
