// DTN Messenger — Chat Screen

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:file_picker/file_picker.dart';
import 'package:intl/intl.dart';
import 'package:photo_view/photo_view.dart';
import 'package:video_player/video_player.dart';
import 'package:just_audio/just_audio.dart';

import '../../core/models/message.dart';
import '../../app/app_theme.dart';
import 'chat_provider.dart';
import '../conversations/conversations_provider.dart';

class ChatScreen extends StatefulWidget {
  final String conversationId;
  final String peerId;
  final String peerName;

  const ChatScreen({
    super.key,
    required this.conversationId,
    required this.peerId,
    required this.peerName,
  });

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _textCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final convsProv = context.read<ConversationsProvider>();
      final chatProv = context.read<ChatProvider>();

      // Ensure conversation record exists.
      await convsProv.ensureConversation(
        conversationId: widget.conversationId,
        peerId: widget.peerId,
        peerName: widget.peerName,
      );

      await chatProv.openConversation(widget.conversationId, convsProv);
      _scrollToBottom();
    });
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _sendText() async {
    final text = _textCtrl.text;
    if (text.trim().isEmpty) return;
    _textCtrl.clear();
    setState(() => _sending = true);
    await context.read<ChatProvider>().sendText(
      conversationId: widget.conversationId,
      recipientId: widget.peerId,
      text: text,
    );
    setState(() => _sending = false);
    _scrollToBottom();
  }

  Future<void> _pickAndSendFile() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['jpg', 'jpeg', 'png', 'webp', 'mp3', 'mp4'],
    );
    if (result == null || result.files.isEmpty) return;
    final path = result.files.single.path;
    if (path == null) {
      _showError('Could not access the selected file.');
      return;
    }

    setState(() => _sending = true);
    final error = await context.read<ChatProvider>().sendAttachment(
      conversationId: widget.conversationId,
      recipientId: widget.peerId,
      filePath: path,
    );
    setState(() => _sending = false);
    if (error != null) _showError(error);
    _scrollToBottom();
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(msg), backgroundColor: Colors.red));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.peerName,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
            Text(
              widget.peerId,
              style: TextStyle(
                fontSize: 11,
                color: Theme.of(context).colorScheme.outline,
              ),
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          Expanded(child: _MessageList(scrollCtrl: _scrollCtrl)),
          _InputBar(
            controller: _textCtrl,
            sending: _sending,
            onSend: _sendText,
            onAttach: _pickAndSendFile,
          ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _textCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Message List
// ─────────────────────────────────────────────────────────────────────────────

class _MessageList extends StatelessWidget {
  final ScrollController scrollCtrl;
  const _MessageList({required this.scrollCtrl});

  @override
  Widget build(BuildContext context) {
    return Consumer<ChatProvider>(
      builder: (_, prov, __) {
        if (prov.loading) {
          return const Center(child: CircularProgressIndicator());
        }
        if (prov.messages.isEmpty) {
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.chat_bubble_outline,
                  size: 56,
                  color: Theme.of(context).colorScheme.outlineVariant,
                ),
                const SizedBox(height: 12),
                Text(
                  'No messages yet — say hello!',
                  style: Theme.of(context).textTheme.bodyMedium
                      ?.copyWith(color: Theme.of(context).colorScheme.outline),
                ),
              ],
            ),
          );
        }
        return ListView.builder(
          controller: scrollCtrl,
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
          itemCount: prov.messages.length,
          itemBuilder: (_, i) => _MessageBubble(msg: prov.messages[i]),
        );
      },
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Message Bubble
// ─────────────────────────────────────────────────────────────────────────────

class _MessageBubble extends StatelessWidget {
  final Message msg;
  const _MessageBubble({required this.msg});

  @override
  Widget build(BuildContext context) {
    final isMine = msg.isMine;
    return Align(
      alignment: isMine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.75,
        ),
        margin: const EdgeInsets.symmetric(vertical: 3, horizontal: 4),
        child: Column(
          crossAxisAlignment: isMine
              ? CrossAxisAlignment.end
              : CrossAxisAlignment.start,
          children: [
            Material(
              color: isMine
                  ? AppTheme.sentBubbleColor(context)
                  : AppTheme.receivedBubbleColor(context),
              borderRadius: BorderRadius.only(
                topLeft: const Radius.circular(18),
                topRight: const Radius.circular(18),
                bottomLeft: Radius.circular(isMine ? 18 : 4),
                bottomRight: Radius.circular(isMine ? 4 : 18),
              ),
              clipBehavior: Clip.hardEdge,
              child: InkWell(
                onLongPress: () => _showMsgDetails(context),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 8,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _bubbleContent(context),
                      const SizedBox(height: 4),
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            DateFormat.Hm().format(msg.createdAt),
                            style: TextStyle(
                              fontSize: 10,
                              color: isMine
                                  ? AppTheme.sentTextColor(context)
                                        .withOpacity(0.7)
                                  : Theme.of(context).colorScheme.outline,
                            ),
                          ),
                          if (isMine) ...[
                            const SizedBox(width: 4),
                            _StatusIcon(status: msg.status),
                          ],
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
            if (msg.status == DeliveryStatus.failed)
              Padding(
                padding: const EdgeInsets.only(top: 2, right: 4),
                child: Consumer<ChatProvider>(
                  builder: (_, prov, __) => GestureDetector(
                    onTap: () => prov.retryMessage(msg.messageId),
                    child: const Text(
                      '⟳ Retry',
                      style: TextStyle(
                        fontSize: 11,
                        color: Colors.red,
                        decoration: TextDecoration.underline,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _bubbleContent(BuildContext context) {
    final textColor = msg.isMine
        ? AppTheme.sentTextColor(context)
        : AppTheme.receivedTextColor(context);

    switch (msg.type) {
      case MessageType.text:
        return Text(msg.textContent ?? '', style: TextStyle(color: textColor));
      case MessageType.image:
        return _ImagePreview(msg: msg);
      case MessageType.audio:
        return _AudioPlayer(msg: msg);
      case MessageType.video:
        return _VideoPlayer(msg: msg);
    }
  }

  void _showMsgDetails(BuildContext context) {
    showModalBottomSheet(
      context: context,
      builder: (_) => _MessageDetails(msg: msg),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Status icon
// ─────────────────────────────────────────────────────────────────────────────

class _StatusIcon extends StatelessWidget {
  final DeliveryStatus status;
  const _StatusIcon({required this.status});

  @override
  Widget build(BuildContext context) {
    switch (status) {
      case DeliveryStatus.localQueued:
        return const Icon(Icons.access_time, size: 12, color: Colors.white70);
      case DeliveryStatus.peerTransferred:
        return const Icon(Icons.done, size: 12, color: Colors.white70);
      case DeliveryStatus.destinationDelivered:
        return const Icon(Icons.done_all, size: 12, color: Colors.white);
      case DeliveryStatus.failed:
        return const Icon(
          Icons.error_outline,
          size: 12,
          color: Colors.redAccent,
        );
      case DeliveryStatus.expired:
        return const Icon(
          Icons.timer_off,
          size: 12,
          color: Colors.orangeAccent,
        );
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Image Preview
// ─────────────────────────────────────────────────────────────────────────────

class _ImagePreview extends StatelessWidget {
  final Message msg;
  const _ImagePreview({required this.msg});

  @override
  Widget build(BuildContext context) {
    final path = msg.attachment?.localPath;
    if (path == null) {
      return const Text('📷 Image (missing)');
    }
    final file = File(path);
    return GestureDetector(
      onTap: () => _openViewer(context, file),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Image.file(
          file,
          width: 200,
          height: 200,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => const SizedBox(
            width: 200,
            height: 100,
            child: Center(child: Icon(Icons.broken_image_outlined, size: 40)),
          ),
        ),
      ),
    );
  }

  void _openViewer(BuildContext context, File file) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => Scaffold(
          backgroundColor: Colors.black,
          appBar: AppBar(
            backgroundColor: Colors.black,
            foregroundColor: Colors.white,
          ),
          body: PhotoView(imageProvider: FileImage(file)),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Audio Player
// ─────────────────────────────────────────────────────────────────────────────

class _AudioPlayer extends StatefulWidget {
  final Message msg;
  const _AudioPlayer({required this.msg});

  @override
  State<_AudioPlayer> createState() => _AudioPlayerState();
}

class _AudioPlayerState extends State<_AudioPlayer> {
  final _player = AudioPlayer();
  bool _playing = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;

  @override
  void initState() {
    super.initState();
    final path = widget.msg.attachment?.localPath;
    if (path != null) {
      _player
          .setFilePath(path)
          .then((_) {
            setState(() => _duration = _player.duration ?? Duration.zero);
          })
          .catchError((_) {});
    }
    _player.positionStream.listen((p) {
      if (mounted) setState(() => _position = p);
    });
    _player.playerStateStream.listen((s) {
      if (mounted) {
        setState(() => _playing = s.playing);
        if (s.processingState == ProcessingState.completed) {
          setState(() {
            _playing = false;
            _position = Duration.zero;
          });
        }
      }
    });
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  String _fmt(Duration d) =>
      '${d.inMinutes.remainder(60).toString().padLeft(2, '0')}:'
      '${d.inSeconds.remainder(60).toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 220,
      child: Row(
        children: [
          IconButton(
            icon: Icon(_playing ? Icons.pause : Icons.play_arrow),
            onPressed: () => _playing ? _player.pause() : _player.play(),
          ),
          Expanded(
            child: Slider(
              value: _duration.inMilliseconds > 0
                  ? _position.inMilliseconds / _duration.inMilliseconds
                  : 0.0,
              onChanged: (v) => _player.seek(
                Duration(milliseconds: (v * _duration.inMilliseconds).round()),
              ),
            ),
          ),
          Text(_fmt(_position), style: const TextStyle(fontSize: 10)),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Video Player
// ─────────────────────────────────────────────────────────────────────────────

class _VideoPlayer extends StatefulWidget {
  final Message msg;
  const _VideoPlayer({required this.msg});

  @override
  State<_VideoPlayer> createState() => _VideoPlayerState();
}

class _VideoPlayerState extends State<_VideoPlayer> {
  VideoPlayerController? _ctrl;
  bool _initialized = false;
  bool _playing = false;

  @override
  void initState() {
    super.initState();
    final path = widget.msg.attachment?.localPath;
    if (path != null) {
      _ctrl = VideoPlayerController.file(File(path))
        ..initialize()
            .then((_) {
              if (mounted) setState(() => _initialized = true);
            })
            .catchError((_) {});
    }
  }

  @override
  void dispose() {
    _ctrl?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_initialized || _ctrl == null) {
      return const SizedBox(
        width: 200,
        height: 120,
        child: Center(child: CircularProgressIndicator()),
      );
    }
    return GestureDetector(
      onTap: () {
        setState(() {
          if (_playing) {
            _ctrl!.pause();
          } else {
            _ctrl!.play();
          }
          _playing = !_playing;
        });
      },
      child: Stack(
        alignment: Alignment.center,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: SizedBox(
              width: 200,
              child: AspectRatio(
                aspectRatio: _ctrl!.value.aspectRatio,
                child: VideoPlayerWidget(controller: _ctrl!),
              ),
            ),
          ),
          if (!_playing)
            Container(
              decoration: BoxDecoration(
                color: Colors.black45,
                shape: BoxShape.circle,
              ),
              padding: const EdgeInsets.all(8),
              child: const Icon(
                Icons.play_arrow,
                color: Colors.white,
                size: 32,
              ),
            ),
        ],
      ),
    );
  }
}

class VideoPlayerWidget extends StatefulWidget {
  final VideoPlayerController controller;
  const VideoPlayerWidget({super.key, required this.controller});

  @override
  State<VideoPlayerWidget> createState() => _VideoPlayerWidgetState();
}

class _VideoPlayerWidgetState extends State<VideoPlayerWidget> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_rebuild);
  }

  void _rebuild() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    widget.controller.removeListener(_rebuild);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => VideoPlayer(widget.controller);
}

// ─────────────────────────────────────────────────────────────────────────────
// Message details sheet
// ─────────────────────────────────────────────────────────────────────────────

class _MessageDetails extends StatelessWidget {
  final Message msg;
  const _MessageDetails({required this.msg});

  @override
  Widget build(BuildContext context) {
    final att = msg.attachment;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Message Details',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const Divider(height: 20),
          _row('ID', msg.messageId),
          _row('Status', msg.status.displayLabel),
          _row('Sent', DateFormat('dd MMM yyyy HH:mm').format(msg.createdAt)),
          _row(
            'Expires',
            DateFormat('dd MMM yyyy HH:mm').format(msg.expiresAt),
          ),
          if (msg.failureReason != null) _row('Failure', msg.failureReason!),
          if (msg.relayPath.isNotEmpty)
            _row('Relay path', msg.relayPath.join(' → ')),
          if (att != null) ...[
            const Divider(height: 16),
            _row('File', att.fileName),
            _row('Type', att.mimeType),
            _row('Size', '${(att.sizeBytes / 1024).toStringAsFixed(1)} KB'),
            _row('SHA-256', att.sha256Hex.substring(0, 16) + '…'),
            if (att.transferProgress != null)
              _row(
                'Transfer',
                '${(att.transferProgress! * 100).toStringAsFixed(0)}%',
              ),
          ],
        ],
      ),
    );
  }

  Widget _row(String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 3),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 100,
          child: Text(
            label,
            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
          ),
        ),
        Expanded(child: Text(value, style: const TextStyle(fontSize: 12))),
      ],
    ),
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Input Bar
// ─────────────────────────────────────────────────────────────────────────────

class _InputBar extends StatelessWidget {
  final TextEditingController controller;
  final bool sending;
  final VoidCallback onSend;
  final VoidCallback onAttach;

  const _InputBar({
    required this.controller,
    required this.sending,
    required this.onSend,
    required this.onAttach,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          border: Border(
            top: BorderSide(color: Theme.of(context).dividerColor),
          ),
        ),
        child: Row(
          children: [
            IconButton(
              icon: const Icon(Icons.attach_file),
              tooltip: 'Attach image / audio / video',
              onPressed: sending ? null : onAttach,
            ),
            Expanded(
              child: TextField(
                controller: controller,
                minLines: 1,
                maxLines: 4,
                textCapitalization: TextCapitalization.sentences,
                decoration: const InputDecoration(hintText: 'Type a message…'),
                onSubmitted: (_) => onSend(),
              ),
            ),
            const SizedBox(width: 6),
            sending
                ? const SizedBox(
                    width: 40,
                    height: 40,
                    child: Padding(
                      padding: EdgeInsets.all(8),
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  )
                : IconButton.filled(
                    icon: const Icon(Icons.send),
                    tooltip: 'Send',
                    onPressed: onSend,
                  ),
          ],
        ),
      ),
    );
  }
}
