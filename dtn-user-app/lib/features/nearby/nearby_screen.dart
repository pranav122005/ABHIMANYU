// DTN Messenger — Nearby Nodes Screen

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/models/peer_node.dart';
import '../conversations/conversations_screen.dart' show buildConversationId;
import '../chat/chat_screen.dart';
import 'nearby_provider.dart';
import '../../core/models/app_config.dart';

class NearbyScreen extends StatefulWidget {
  const NearbyScreen({super.key});

  @override
  State<NearbyScreen> createState() => _NearbyScreenState();
}

class _NearbyScreenState extends State<NearbyScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => context.read<NearbyProvider>().scan(),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Nearby Nodes'),
        actions: [
          Consumer<NearbyProvider>(
            builder: (_, prov, __) => IconButton(
              icon: prov.state == DiscoveryState.scanning
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh),
              tooltip: 'Scan',
              onPressed: prov.state == DiscoveryState.scanning
                  ? null
                  : prov.scan,
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          _SimBanner(),
          Expanded(child: _PeerList()),
        ],
      ),
    );
  }
}

class _SimBanner extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Consumer<NearbyProvider>(
      builder: (_, prov, __) {
        if (!prov.isSimulated) return const SizedBox.shrink();
        return Container(
          width: double.infinity,
          color: Colors.orange.shade100,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            children: [
              const Icon(
                Icons.warning_amber_outlined,
                size: 16,
                color: Colors.deepOrange,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'SIMULATION MODE — Peers below are synthetic test nodes. '
                  'No real DTN hardware connected.',
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.deepOrange.shade900,
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _PeerList extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Consumer<NearbyProvider>(
      builder: (_, prov, __) {
        if (prov.state == DiscoveryState.scanning) {
          return const Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                CircularProgressIndicator(),
                SizedBox(height: 16),
                Text('Scanning for nearby DTN nodes…'),
              ],
            ),
          );
        }

        if (prov.state == DiscoveryState.error) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.wifi_off, size: 56, color: Colors.red),
                  const SizedBox(height: 16),
                  Text(
                    prov.error ?? 'Discovery failed',
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                  ElevatedButton.icon(
                    onPressed: prov.scan,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Retry'),
                  ),
                ],
              ),
            ),
          );
        }

        if (prov.peers.isEmpty) {
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.wifi_find,
                  size: 64,
                  color: Theme.of(context).colorScheme.outlineVariant,
                ),
                const SizedBox(height: 16),
                const Text('No nearby nodes found.'),
                const SizedBox(height: 8),
                ElevatedButton.icon(
                  onPressed: prov.scan,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Scan again'),
                ),
              ],
            ),
          );
        }

        return ListView.separated(
          padding: const EdgeInsets.symmetric(vertical: 8),
          itemCount: prov.peers.length,
          separatorBuilder: (_, __) => const Divider(height: 0),
          itemBuilder: (_, i) => _PeerTile(peer: prov.peers[i]),
        );
      },
    );
  }
}

class _PeerTile extends StatelessWidget {
  final PeerNode peer;
  const _PeerTile({required this.peer});

  @override
  Widget build(BuildContext context) {
    final prov = context.read<NearbyProvider>();
    final config = context.read<AppConfig>();
    final connErr = prov.connectionErrors[peer.nodeId];
    final color = _reachabilityColor(peer.reachability);

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      leading: Stack(
        children: [
          CircleAvatar(
            backgroundColor: color.withOpacity(0.15),
            child: Icon(Icons.router, color: color),
          ),
          if (peer.isSimulated)
            const Positioned(
              right: 0,
              bottom: 0,
              child: Icon(Icons.science, size: 12, color: Colors.orange),
            ),
        ],
      ),
      title: Text(
        peer.effectiveName,
        style: const TextStyle(fontWeight: FontWeight.w600),
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: color.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: color.withOpacity(0.4)),
                ),
                child: Text(
                  peer.reachability.label,
                  style: TextStyle(
                    fontSize: 10,
                    color: color,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                peer.discoveryMethod.label,
                style: const TextStyle(fontSize: 11),
              ),
            ],
          ),
          if (peer.address != null)
            Text(
              '${peer.address}${peer.port != null ? ':${peer.port}' : ''}',
              style: const TextStyle(fontSize: 11),
            ),
          Text(
            'Last seen: ${_ago(peer.lastSeen)}',
            style: const TextStyle(fontSize: 11),
          ),
          if (connErr != null)
            Text(
              '⚠ $connErr',
              style: const TextStyle(fontSize: 11, color: Colors.red),
            ),
        ],
      ),
      trailing:
          peer.reachability == PeerReachability.connected ||
              peer.reachability == PeerReachability.dtnReachable
          ? PopupMenuButton<String>(
              onSelected: (v) async {
                if (v == 'chat') {
                  final convId = buildConversationId(
                    config.nodeId,
                    peer.nodeId,
                  );
                  if (context.mounted) {
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => ChatScreen(
                          conversationId: convId,
                          peerId: peer.nodeId,
                          peerName: peer.effectiveName,
                        ),
                      ),
                    );
                  }
                } else if (v == 'disconnect') {
                  await prov.disconnect(peer.nodeId);
                }
              },
              itemBuilder: (_) => [
                const PopupMenuItem(value: 'chat', child: Text('Open chat')),
                const PopupMenuItem(
                  value: 'disconnect',
                  child: Text('Disconnect'),
                ),
              ],
            )
          : OutlinedButton(
              onPressed: () async {
                final ok = await prov.connectToPeer(peer);
                if (ok && context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('Connected to ${peer.effectiveName}'),
                    ),
                  );
                }
              },
              child: Text(
                peer.reachability == PeerReachability.unreachable
                    ? 'Retry'
                    : 'Connect',
                style: const TextStyle(fontSize: 12),
              ),
            ),
    );
  }

  Color _reachabilityColor(PeerReachability r) {
    switch (r) {
      case PeerReachability.dtnReachable:
        return Colors.green;
      case PeerReachability.connected:
        return Colors.blue;
      case PeerReachability.discovered:
        return Colors.orange;
      case PeerReachability.unreachable:
        return Colors.red;
      case PeerReachability.stale:
        return Colors.grey;
    }
  }

  String _ago(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inSeconds < 60) return '${diff.inSeconds}s ago';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    return '${diff.inHours}h ago';
  }
}
