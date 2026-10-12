// DTN Messenger — Outbox / Transfer Queue Screen

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';

import '../../core/models/message.dart';
import 'outbox_provider.dart';

class OutboxScreen extends StatefulWidget {
  const OutboxScreen({super.key});

  @override
  State<OutboxScreen> createState() => _OutboxScreenState();
}

class _OutboxScreenState extends State<OutboxScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 4, vsync: this);
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => context.read<OutboxProvider>().load(),
    );
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Outbox & Transfer Queue'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => context.read<OutboxProvider>().load(),
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          isScrollable: true,
          tabs: const [
            Tab(text: 'Queued'),
            Tab(text: 'In Transit'),
            Tab(text: 'Failed'),
            Tab(text: 'Expired'),
          ],
        ),
      ),
      body: Consumer<OutboxProvider>(
        builder: (_, prov, __) {
          if (prov.loading) {
            return const Center(child: CircularProgressIndicator());
          }
          return TabBarView(
            controller: _tabs,
            children: [
              _MessageTab(
                messages: prov.queued,
                emptyMessage: 'No messages queued.',
                emptyIcon: Icons.inbox_outlined,
              ),
              _MessageTab(
                messages: prov.inTransit,
                emptyMessage: 'Nothing in transit.',
                emptyIcon: Icons.swap_horiz,
              ),
              _MessageTab(
                messages: prov.failed,
                emptyMessage: 'No failed messages.',
                emptyIcon: Icons.check_circle_outline,
                showRetry: true,
              ),
              _MessageTab(
                messages: prov.expired,
                emptyMessage: 'No expired messages.',
                emptyIcon: Icons.timer_off_outlined,
              ),
            ],
          );
        },
      ),
    );
  }
}

class _MessageTab extends StatelessWidget {
  final List<Message> messages;
  final String emptyMessage;
  final IconData emptyIcon;
  final bool showRetry;

  const _MessageTab({
    required this.messages,
    required this.emptyMessage,
    required this.emptyIcon,
    this.showRetry = false,
  });

  @override
  Widget build(BuildContext context) {
    if (messages.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              emptyIcon,
              size: 56,
              color: Theme.of(context).colorScheme.outlineVariant,
            ),
            const SizedBox(height: 12),
            Text(emptyMessage, style: Theme.of(context).textTheme.bodyMedium),
          ],
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: messages.length,
      separatorBuilder: (_, __) => const Divider(height: 0, indent: 72),
      itemBuilder: (_, i) =>
          _OutboxTile(msg: messages[i], showRetry: showRetry),
    );
  }
}

class _OutboxTile extends StatelessWidget {
  final Message msg;
  final bool showRetry;

  const _OutboxTile({required this.msg, required this.showRetry});

  @override
  Widget build(BuildContext context) {
    final prov = context.read<OutboxProvider>();
    final att = msg.attachment;

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      leading: CircleAvatar(
        backgroundColor: _statusColor(msg.status).withOpacity(0.12),
        child: Icon(_typeIcon(msg.type), color: _statusColor(msg.status)),
      ),
      title: Row(
        children: [
          Expanded(
            child: Text(
              _preview(msg),
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w500),
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: _statusColor(msg.status).withOpacity(0.12),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(
              msg.status.displayLabel,
              style: TextStyle(
                fontSize: 11,
                color: _statusColor(msg.status),
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('To: ${msg.recipientId}', style: const TextStyle(fontSize: 11)),
          Text(
            'Created: ${DateFormat('dd MMM HH:mm').format(msg.createdAt)}  '
            'Expires: ${DateFormat('dd MMM HH:mm').format(msg.expiresAt)}',
            style: const TextStyle(fontSize: 11),
          ),
          if (att != null)
            Text(
              '${att.fileName}  ${(att.sizeBytes / 1024).toStringAsFixed(0)} KB',
              style: const TextStyle(fontSize: 11),
            ),
          if (msg.failureReason != null)
            Text(
              '⚠ ${msg.failureReason}',
              style: const TextStyle(fontSize: 11, color: Colors.red),
            ),
          if (msg.relayPath.isNotEmpty)
            Text(
              '↪ ${msg.relayPath.join(' → ')}',
              style: const TextStyle(fontSize: 11),
              overflow: TextOverflow.ellipsis,
            ),
        ],
      ),
      trailing: showRetry && msg.status == DeliveryStatus.failed
          ? IconButton(
              icon: const Icon(Icons.refresh, color: Colors.blue),
              tooltip: 'Retry',
              onPressed: () => prov.retry(msg.messageId),
            )
          : null,
    );
  }

  String _preview(Message m) {
    if (m.type == MessageType.text) {
      return m.textContent?.substring(
            0,
            (m.textContent!.length > 50) ? 50 : m.textContent!.length,
          ) ??
          '';
    }
    if (m.type == MessageType.image)
      return '📷 ${m.attachment?.fileName ?? 'Image'}';
    if (m.type == MessageType.audio)
      return '🎵 ${m.attachment?.fileName ?? 'Audio'}';
    if (m.type == MessageType.video)
      return '🎬 ${m.attachment?.fileName ?? 'Video'}';
    return 'Message';
  }

  IconData _typeIcon(MessageType t) {
    switch (t) {
      case MessageType.text:
        return Icons.chat_bubble_outline;
      case MessageType.image:
        return Icons.image_outlined;
      case MessageType.audio:
        return Icons.music_note_outlined;
      case MessageType.video:
        return Icons.videocam_outlined;
    }
  }

  Color _statusColor(DeliveryStatus s) {
    switch (s) {
      case DeliveryStatus.localQueued:
        return Colors.blue;
      case DeliveryStatus.peerTransferred:
        return Colors.teal;
      case DeliveryStatus.destinationDelivered:
        return Colors.green;
      case DeliveryStatus.failed:
        return Colors.red;
      case DeliveryStatus.expired:
        return Colors.orange;
    }
  }
}
