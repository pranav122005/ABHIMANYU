// DTN Messenger — DTN Transport Client Interface
// Defines the abstract contract that the UI layer talks to.
// Concrete implementations: SimulatedDtnClient, HttpDtnClient (future).

import '../models/message.dart';
import '../models/peer_node.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Result / Error types
// ─────────────────────────────────────────────────────────────────────────────

/// Outcome of a transport operation.
class TransportResult<T> {
  final T? value;
  final String? error;
  bool get isOk => error == null;

  const TransportResult.ok(this.value) : error = null;
  const TransportResult.err(this.error) : value = null;

  @override
  String toString() => isOk ? 'OK($value)' : 'ERR($error)';
}

// ─────────────────────────────────────────────────────────────────────────────
// Delivery event (inbound from transport)
// ─────────────────────────────────────────────────────────────────────────────

class DeliveryEvent {
  final String messageId;
  final DeliveryStatus newStatus;
  final String? failureReason;
  final List<String>? relayPath;

  const DeliveryEvent({
    required this.messageId,
    required this.newStatus,
    this.failureReason,
    this.relayPath,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Abstract DTN Client
// ─────────────────────────────────────────────────────────────────────────────

/// Abstract transport client.  The UI layer depends only on this interface.
/// Routing decisions are NOT made here — they belong to the existing DTN engine.
abstract class DtnClient {
  /// Whether this client is using a real endpoint or simulation.
  bool get isSimulated;

  /// Human-readable description of the connection mode.
  String get connectionDescription;

  // ── Discovery ─────────────────────────────────────────────────────────────

  /// Perform a single discovery scan and return discovered peers.
  /// The app must not fabricate peers — return only genuinely found nodes,
  /// or clearly-labelled simulation peers.
  Future<TransportResult<List<PeerNode>>> discoverPeers();

  // ── Session ───────────────────────────────────────────────────────────────

  /// Request a peer session (connect / handshake).
  Future<TransportResult<void>> requestSession(PeerNode peer);

  /// Gracefully close a session with a peer.
  Future<TransportResult<void>> closeSession(String nodeId);

  // ── Messaging ─────────────────────────────────────────────────────────────

  /// Submit a message bundle to the transport layer.
  /// Returns immediately; delivery events arrive via [deliveryEvents].
  Future<TransportResult<void>> submitMessage(Message message);

  /// Retrieve messages the transport has received for this node.
  Future<TransportResult<List<Message>>> receiveMessages();

  /// Poll the status of a specific outgoing message.
  Future<TransportResult<DeliveryEvent>> queryMessageStatus(String messageId);

  // ── Events ────────────────────────────────────────────────────────────────

  /// Stream of delivery status updates from the transport layer.
  Stream<DeliveryEvent> get deliveryEvents;

  // ── Diagnostics ───────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getDiagnostics();

  Future<void> dispose();
}
