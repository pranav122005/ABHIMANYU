// DTN Messenger — Nearby Nodes Provider

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/models/peer_node.dart';
import '../../core/transport/dtn_client.dart';

enum DiscoveryState { idle, scanning, done, error }

class NearbyProvider extends ChangeNotifier {
  final DtnClient _client;

  NearbyProvider(this._client);

  List<PeerNode> _peers = [];
  DiscoveryState _state = DiscoveryState.idle;
  String? _error;
  final Map<String, String> _connectionErrors = {};

  List<PeerNode> get peers => _peers;
  DiscoveryState get state => _state;
  String? get error => _error;
  Map<String, String> get connectionErrors => _connectionErrors;

  bool get isSimulated => _client.isSimulated;
  String get connectionDescription => _client.connectionDescription;

  Future<void> scan() async {
    _state = DiscoveryState.scanning;
    _error = null;
    notifyListeners();

    final result = await _client.discoverPeers();
    if (result.isOk) {
      _peers = result.value ?? [];
      _state = DiscoveryState.done;
    } else {
      _error = result.error;
      _state = DiscoveryState.error;
    }
    notifyListeners();
  }

  Future<bool> connectToPeer(PeerNode peer) async {
    _connectionErrors.remove(peer.nodeId);
    notifyListeners();

    final result = await _client.requestSession(peer);
    if (result.isOk) {
      final idx = _peers.indexOf(peer);
      if (idx != -1) {
        _peers[idx] = peer.copyWith(
          reachability: PeerReachability.connected,
          lastSeenMs: DateTime.now().toUtc().millisecondsSinceEpoch,
        );
        notifyListeners();
      }
      return true;
    }
    _connectionErrors[peer.nodeId] = result.error ?? 'Connection failed.';
    notifyListeners();
    return false;
  }

  Future<void> disconnect(String nodeId) async {
    await _client.closeSession(nodeId);
    final idx = _peers.indexWhere((p) => p.nodeId == nodeId);
    if (idx != -1) {
      _peers[idx] = _peers[idx].copyWith(
        reachability: PeerReachability.discovered,
      );
      notifyListeners();
    }
  }
}
