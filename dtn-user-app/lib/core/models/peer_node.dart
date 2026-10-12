// DTN Messenger — Peer Node Model
// Represents a discovered nearby DTN node.

/// How the node was discovered.
enum DiscoveryMethod { wifi, simulation, manual }

extension DiscoveryMethodX on DiscoveryMethod {
  String get label {
    switch (this) {
      case DiscoveryMethod.wifi:
        return 'Wi-Fi LAN';
      case DiscoveryMethod.simulation:
        return 'Simulation';
      case DiscoveryMethod.manual:
        return 'Manual';
    }
  }

  String toJson() => name;
  static DiscoveryMethod fromJson(String s) => DiscoveryMethod.values
      .firstWhere((e) => e.name == s, orElse: () => DiscoveryMethod.wifi);
}

/// Reachability state of the peer from the app's perspective.
enum PeerReachability {
  /// Discovered but not yet connected.
  discovered,

  /// Transport-level connection established.
  connected,

  /// DTN bundle exchange handshake completed — messages can be exchanged.
  dtnReachable,

  /// Connection attempt failed.
  unreachable,

  /// Previously seen but not currently visible.
  stale,
}

extension PeerReachabilityX on PeerReachability {
  String get label {
    switch (this) {
      case PeerReachability.discovered:
        return 'Discovered';
      case PeerReachability.connected:
        return 'Connected';
      case PeerReachability.dtnReachable:
        return 'DTN Reachable';
      case PeerReachability.unreachable:
        return 'Unreachable';
      case PeerReachability.stale:
        return 'Stale';
    }
  }
}

/// A nearby DTN-compatible node discovered via local network or simulation.
class PeerNode {
  /// Unique node identifier (e.g., hostname, UUID, or hardware MAC).
  final String nodeId;

  /// Human-friendly display name, if advertised.
  final String? displayName;

  /// IP address or other transport address.
  final String? address;

  /// Transport port (for IP-based transports).
  final int? port;

  /// How the node was found.
  final DiscoveryMethod discoveryMethod;

  /// Current reachability state.
  final PeerReachability reachability;

  /// UTC ms when the node was last observed.
  final int lastSeenMs;

  /// Connection error message, if the last attempt failed.
  final String? lastError;

  /// True when this is a deterministic test peer (never a real device).
  final bool isSimulated;

  const PeerNode({
    required this.nodeId,
    this.displayName,
    this.address,
    this.port,
    required this.discoveryMethod,
    this.reachability = PeerReachability.discovered,
    required this.lastSeenMs,
    this.lastError,
    this.isSimulated = false,
  });

  String get effectiveName => displayName ?? nodeId;

  bool get isStale {
    final ageMs = DateTime.now().toUtc().millisecondsSinceEpoch - lastSeenMs;
    return ageMs > 5 * 60 * 1000; // > 5 minutes
  }

  DateTime get lastSeen =>
      DateTime.fromMillisecondsSinceEpoch(lastSeenMs, isUtc: true).toLocal();

  PeerNode copyWith({
    PeerReachability? reachability,
    int? lastSeenMs,
    String? lastError,
  }) => PeerNode(
    nodeId: nodeId,
    displayName: displayName,
    address: address,
    port: port,
    discoveryMethod: discoveryMethod,
    reachability: reachability ?? this.reachability,
    lastSeenMs: lastSeenMs ?? this.lastSeenMs,
    lastError: lastError ?? this.lastError,
    isSimulated: isSimulated,
  );

  @override
  bool operator ==(Object other) => other is PeerNode && other.nodeId == nodeId;

  @override
  int get hashCode => nodeId.hashCode;
}
