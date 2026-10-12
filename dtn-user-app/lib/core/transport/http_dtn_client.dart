// DTN Messenger — HTTP DTN Client (Stub)
// ─────────────────────────────────────────────────────────────────────────────
// STUB — Not yet implemented.
// This client would connect to a real DTN gateway HTTP/WebSocket API.
//
// Required backend contract:
//   POST   /api/v1/message/submit        → submit outgoing bundle
//   GET    /api/v1/message/receive       → poll inbound bundles
//   GET    /api/v1/message/{id}/status   → query delivery state
//   GET    /api/v1/peers                 → list discovered peers
//   POST   /api/v1/session/request       → request peer session
//   DELETE /api/v1/session/{nodeId}      → close session
//   WS     /api/v1/events                → push delivery events
//
// Until the backend exposes these endpoints and a compatible radio transport
// is deployed on the ESP8266 nodes, this client cannot be made functional.
// Use SimulatedDtnClient for development and testing.
// ─────────────────────────────────────────────────────────────────────────────

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/message.dart';
import '../models/peer_node.dart';
import 'dtn_client.dart';

class HttpDtnClient implements DtnClient {
  final String baseUrl;
  final String localNodeId;
  final Duration timeout;

  final _eventController = StreamController<DeliveryEvent>.broadcast();
  Timer? _pollTimer;

  HttpDtnClient({
    required this.baseUrl,
    required this.localNodeId,
    this.timeout = const Duration(seconds: 10),
  });

  @override
  bool get isSimulated => false;

  @override
  String get connectionDescription => 'DTN Gateway: $baseUrl';

  @override
  Future<TransportResult<List<PeerNode>>> discoverPeers() async {
    try {
      final resp = await http
          .get(Uri.parse('$baseUrl/api/v1/peers'))
          .timeout(timeout);
      if (resp.statusCode == 200) {
        // TODO: map JSON → PeerNode once backend format is defined.
        return const TransportResult.ok([]);
      }
      return TransportResult.err(
        'Gateway returned ${resp.statusCode}: ${resp.body}',
      );
    } catch (e) {
      return TransportResult.err('Peer discovery failed: $e');
    }
  }

  @override
  Future<TransportResult<void>> requestSession(PeerNode peer) async {
    try {
      final resp = await http
          .post(
            Uri.parse('$baseUrl/api/v1/session/request'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'nodeId': peer.nodeId}),
          )
          .timeout(timeout);
      if (resp.statusCode == 200 || resp.statusCode == 201) {
        return const TransportResult.ok(null);
      }
      return TransportResult.err(
        'Session request failed ${resp.statusCode}: ${resp.body}',
      );
    } catch (e) {
      return TransportResult.err('Session request error: $e');
    }
  }

  @override
  Future<TransportResult<void>> closeSession(String nodeId) async {
    try {
      await http
          .delete(Uri.parse('$baseUrl/api/v1/session/$nodeId'))
          .timeout(timeout);
      return const TransportResult.ok(null);
    } catch (e) {
      return TransportResult.err('Close session error: $e');
    }
  }

  @override
  Future<TransportResult<void>> submitMessage(Message message) async {
    try {
      final resp = await http
          .post(
            Uri.parse('$baseUrl/api/v1/message/submit'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(message.toJson()),
          )
          .timeout(timeout);
      if (resp.statusCode == 200 || resp.statusCode == 202) {
        return const TransportResult.ok(null);
      }
      return TransportResult.err(
        'Submit failed ${resp.statusCode}: ${resp.body}',
      );
    } catch (e) {
      return TransportResult.err('Submit error: $e');
    }
  }

  @override
  Future<TransportResult<List<Message>>> receiveMessages() async {
    try {
      final resp = await http
          .get(Uri.parse('$baseUrl/api/v1/message/receive?node=$localNodeId'))
          .timeout(timeout);
      if (resp.statusCode == 200) {
        final list = jsonDecode(resp.body) as List;
        final msgs = list
            .map((e) => Message.fromJson(e as Map<String, dynamic>))
            .toList();
        return TransportResult.ok(msgs);
      }
      return TransportResult.err(
        'Receive failed ${resp.statusCode}: ${resp.body}',
      );
    } catch (e) {
      return TransportResult.err('Receive error: $e');
    }
  }

  @override
  Future<TransportResult<DeliveryEvent>> queryMessageStatus(
    String messageId,
  ) async {
    try {
      final resp = await http
          .get(Uri.parse('$baseUrl/api/v1/message/$messageId/status'))
          .timeout(timeout);
      if (resp.statusCode == 200) {
        final j = jsonDecode(resp.body) as Map<String, dynamic>;
        return TransportResult.ok(
          DeliveryEvent(
            messageId: messageId,
            newStatus: DeliveryStatusX.fromJson(j['status'] as String),
            failureReason: j['failureReason'] as String?,
            relayPath: (j['relayPath'] as List?)?.cast<String>(),
          ),
        );
      }
      return TransportResult.err('Status query ${resp.statusCode}');
    } catch (e) {
      return TransportResult.err('Status query error: $e');
    }
  }

  @override
  Stream<DeliveryEvent> get deliveryEvents => _eventController.stream;

  void startPolling(Duration interval) {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(interval, (_) => _pollStatuses());
  }

  Future<void> _pollStatuses() async {
    // TODO: implement polling or upgrade to WebSocket.
  }

  @override
  Future<Map<String, dynamic>> getDiagnostics() async => {
    'mode': 'HTTP_GATEWAY',
    'base_url': baseUrl,
    'local_node_id': localNodeId,
    'status': 'STUB — not yet implemented',
  };

  @override
  Future<void> dispose() async {
    _pollTimer?.cancel();
    await _eventController.close();
  }
}
