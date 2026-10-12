// DTN Messenger — Conversations Screen

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';

import '../../core/models/conversation.dart';
import '../../core/models/message.dart';
import '../../core/models/app_config.dart';
export '../../core/models/message.dart' show buildConversationId;
import '../conversations/conversations_provider.dart';
import '../chat/chat_screen.dart';
import '../nearby/nearby_screen.dart';
import '../outbox/outbox_screen.dart';
import '../settings/settings_screen.dart';

class ConversationsScreen extends StatefulWidget {
  const ConversationsScreen({super.key});

  @override
  State<ConversationsScreen> createState() => _ConversationsScreenState();
}

class _ConversationsScreenState extends State<ConversationsScreen> {
  final _searchCtrl = TextEditingController();
  String _query = '';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<ConversationsProvider>().loadConversations();
    });
    _searchCtrl.addListener(() {
      setState(() => _query = _searchCtrl.text);
    });
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'DTN Messenger',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.wifi_tethering),
            tooltip: 'Nearby Nodes',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const NearbyScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.outbox_outlined),
            tooltip: 'Outbox',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const OutboxScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            tooltip: 'Settings',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const SettingsScreen()),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          _SearchBar(controller: _searchCtrl),
          Expanded(child: _ConversationList(query: _query)),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        tooltip: 'New Conversation',
        onPressed: () => _showNewConversationDialog(context),
        child: const Icon(Icons.edit_outlined),
      ),
    );
  }

  void _showNewConversationDialog(BuildContext context) {
    final nodeIdCtrl = TextEditingController();
    final nameCtrl = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('New Conversation'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nodeIdCtrl,
              decoration: const InputDecoration(
                labelText: 'Peer Node ID or address',
              ),
            ),
            const SizedBox(height: 12),

            TextField(
              controller: nameCtrl,
              decoration: const InputDecoration(labelText: 'Display name'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              final peerId = nodeIdCtrl.text.trim();
              final peerName = nameCtrl.text.trim().isEmpty
                  ? peerId
                  : nameCtrl.text.trim();
              if (peerId.isEmpty) return;
              Navigator.pop(ctx);

              final localNodeId = context.read<AppConfig>().nodeId;
              final convId = buildConversationId(localNodeId, peerId);

              if (!mounted) return;
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => ChatScreen(
                    conversationId: convId,
                    peerId: peerId,
                    peerName: peerName,
                  ),
                ),
              );
            },
            child: const Text('Open'),
          ),
        ],
      ),
    );
  }
}

class _SearchBar extends StatelessWidget {
  final TextEditingController controller;
  const _SearchBar({required this.controller});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: TextField(
        controller: controller,
        decoration: InputDecoration(
          hintText: 'Search conversations…',
          prefixIcon: const Icon(Icons.search, size: 20),
          suffixIcon: controller.text.isNotEmpty
              ? IconButton(
                  icon: const Icon(Icons.clear, size: 18),
                  onPressed: controller.clear,
                )
              : null,
        ),
      ),
    );
  }
}

class _ConversationList extends StatelessWidget {
  final String query;
  const _ConversationList({required this.query});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationsProvider>(
      builder: (_, prov, __) {
        if (prov.loading) {
          return const Center(child: CircularProgressIndicator());
        }
        if (prov.error != null) {
          return _ErrorState(
            message: prov.error!,
            onRetry: prov.loadConversations,
          );
        }
        final convs = prov.search(query);
        if (convs.isEmpty) {
          return _EmptyState(searching: query.isNotEmpty);
        }
        return ListView.separated(
          itemCount: convs.length,
          separatorBuilder: (_, __) => const Divider(height: 0, indent: 72),
          itemBuilder: (_, i) => _ConversationTile(conv: convs[i]),
        );
      },
    );
  }
}

class _ConversationTile extends StatelessWidget {
  final Conversation conv;
  const _ConversationTile({required this.conv});

  @override
  Widget build(BuildContext context) {
    final last = conv.lastMessage;
    final theme = Theme.of(context);

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      leading: CircleAvatar(
        backgroundColor: theme.colorScheme.primaryContainer,
        radius: 26,
        child: Text(
          conv.peerAvatar ??
              (conv.peerName.isNotEmpty ? conv.peerName[0].toUpperCase() : '?'),
          style: TextStyle(
            fontSize: 20,
            color: theme.colorScheme.onPrimaryContainer,
          ),
        ),
      ),
      title: Row(
        children: [
          Expanded(
            child: Text(
              conv.peerName,
              style: const TextStyle(fontWeight: FontWeight.w600),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (last != null)
            Text(
              _formatTime(last.createdAt),
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.outline,
              ),
            ),
        ],
      ),
      subtitle: last == null
          ? const Text(
              'No messages yet',
              style: TextStyle(fontStyle: FontStyle.italic),
            )
          : Row(
              children: [
                if (last.isMine) ...[
                  _StatusIcon(status: last.status),
                  const SizedBox(width: 4),
                ],
                Expanded(
                  child: Text(
                    _preview(last),
                    overflow: TextOverflow.ellipsis,
                    maxLines: 1,
                    style: TextStyle(
                      color: conv.unreadCount > 0
                          ? theme.colorScheme.primary
                          : null,
                      fontWeight: conv.unreadCount > 0
                          ? FontWeight.w600
                          : FontWeight.normal,
                    ),
                  ),
                ),
                if (conv.unreadCount > 0)
                  Container(
                    margin: const EdgeInsets.only(left: 6),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 7,
                      vertical: 2,
                    ),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      '${conv.unreadCount}',
                      style: TextStyle(
                        fontSize: 11,
                        color: theme.colorScheme.onPrimary,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
              ],
            ),
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ChatScreen(
            conversationId: conv.conversationId,
            peerId: conv.peerId,
            peerName: conv.peerName,
          ),
        ),
      ),
    );
  }

  String _preview(Message m) {
    if (m.type == MessageType.text) return m.textContent ?? '';
    if (m.type == MessageType.image) return '📷 Photo';
    if (m.type == MessageType.audio) return '🎵 Audio';
    if (m.type == MessageType.video) return '🎬 Video';
    return 'Attachment';
  }

  String _formatTime(DateTime dt) {
    final now = DateTime.now();
    if (dt.day == now.day && dt.month == now.month && dt.year == now.year) {
      return DateFormat.Hm().format(dt);
    }
    if (now.difference(dt).inDays < 7) {
      return DateFormat.E().format(dt);
    }
    return DateFormat('dd/MM').format(dt);
  }
}

class _StatusIcon extends StatelessWidget {
  final DeliveryStatus status;
  const _StatusIcon({required this.status});

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.outline;
    switch (status) {
      case DeliveryStatus.localQueued:
        return Icon(Icons.access_time, size: 14, color: color);
      case DeliveryStatus.peerTransferred:
        return Icon(Icons.done, size: 14, color: color);
      case DeliveryStatus.destinationDelivered:
        return Icon(
          Icons.done_all,
          size: 14,
          color: Theme.of(context).colorScheme.primary,
        );
      case DeliveryStatus.failed:
        return const Icon(Icons.error_outline, size: 14, color: Colors.red);
      case DeliveryStatus.expired:
        return const Icon(
          Icons.timer_off_outlined,
          size: 14,
          color: Colors.orange,
        );
    }
  }
}

class _EmptyState extends StatelessWidget {
  final bool searching;
  const _EmptyState({required this.searching});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            searching ? Icons.search_off : Icons.chat_bubble_outline,
            size: 64,
            color: Theme.of(context).colorScheme.outline,
          ),
          const SizedBox(height: 16),
          Text(
            searching ? 'No matching conversations' : 'No conversations yet',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          if (!searching)
            Text(
              'Tap the edit button below to start one.',
              style: TextStyle(color: Theme.of(context).colorScheme.outline),
            ),
        ],
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorState({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, size: 48, color: Colors.red),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}
