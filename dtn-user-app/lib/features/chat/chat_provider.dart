// DTN Messenger — Chat Provider

import 'dart:io';
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:mime/mime.dart';
import 'package:crypto/crypto.dart';
import 'package:uuid/uuid.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../../core/models/message.dart';
import '../../core/persistence/app_database.dart';
import '../../core/transport/dtn_client.dart';
import '../../core/models/app_config.dart';
import '../conversations/conversations_provider.dart';

class ChatProvider extends ChangeNotifier {
  final AppDatabase _db;
  final DtnClient _client;
  final AppConfig _config;
  final ConversationsProvider _convsProvider;

  ChatProvider(this._db, this._client, this._config, this._convsProvider);

  // ── State ─────────────────────────────────────────────────────────────────

  List<Message> _messages = [];
  bool _loading = false;
  bool _sending = false;
  String? _error;
  String? _currentConvId;
  StreamSubscription<DeliveryEvent>? _eventSub;

  List<Message> get messages => _messages;
  bool get loading => _loading;
  bool get sending => _sending;
  String? get error => _error;

  // ── Load conversation ──────────────────────────────────────────────────────

  Future<void> openConversation(
    String conversationId,
    ConversationsProvider convsProvider,
  ) async {
    if (_currentConvId == conversationId) return;
    _currentConvId = conversationId;
    _messages = [];
    _loading = true;
    notifyListeners();

    try {
      _messages = await _db.getMessages(conversationId);
    } catch (e) {
      _error = 'Failed to load messages: $e';
    } finally {
      _loading = false;
      notifyListeners();
    }

    await convsProvider.markRead(conversationId);
    _subscribeToEvents();
  }

  void _subscribeToEvents() {
    _eventSub?.cancel();
    _eventSub = _client.deliveryEvents.listen(_handleDeliveryEvent);
  }

  Future<void> _handleDeliveryEvent(DeliveryEvent event) async {
    await _db.updateMessageStatus(
      event.messageId,
      event.newStatus,
      failureReason: event.failureReason,
      relayPath: event.relayPath,
    );
    final idx = _messages.indexWhere((m) => m.messageId == event.messageId);
    if (idx != -1) {
      _messages[idx] = _messages[idx].copyWith(
        status: event.newStatus,
        failureReason: event.failureReason,
        relayPath: event.relayPath ?? _messages[idx].relayPath,
      );
      notifyListeners();
    }
  }

  // ── Send text ─────────────────────────────────────────────────────────────

  Future<void> sendText({
    required String conversationId,
    required String recipientId,
    required String text,
  }) async {
    if (text.trim().isEmpty) return;
    _error = null;

    final msg = Message.createText(
      conversationId: conversationId,
      senderId: _config.nodeId,
      recipientId: recipientId,
      text: text.trim(),
    );

    await _db.insertMessage(msg);
    _messages = [..._messages, msg];
    notifyListeners();
    await _convsProvider.updateLastMessage(msg);

    final result = await _client.submitMessage(msg);
    if (!result.isOk) {
      await _db.updateMessageStatus(
        msg.messageId,
        DeliveryStatus.failed,
        failureReason: result.error,
      );
      final idx = _messages.indexWhere((m) => m.messageId == msg.messageId);
      if (idx != -1) {
        _messages[idx] = _messages[idx].copyWith(
          status: DeliveryStatus.failed,
          failureReason: result.error,
        );
        notifyListeners();
      }
    }
  }

  // ── Send attachment ────────────────────────────────────────────────────────

  Future<String?> sendAttachment({
    required String conversationId,
    required String recipientId,
    required String filePath,
  }) async {
    final file = File(filePath);
    if (!await file.exists()) return 'File not found.';

    final bytes = await file.readAsBytes();
    final mimeType =
        lookupMimeType(filePath, headerBytes: bytes.sublist(0, 12)) ??
        'application/octet-stream';

    final validationError = validateAttachment(
      mimeType,
      bytes.length,
      maxBytes: _config.maxAttachmentBytes,
    );
    if (validationError != null) return validationError;

    // Copy file to app storage so it remains accessible.
    final appDir = await getApplicationDocumentsDirectory();
    final attachDir = Directory(
      p.join(appDir.path, 'DTNMessenger', 'attachments'),
    );
    await attachDir.create(recursive: true);
    final fileName = p.basename(filePath);
    final storedPath = p.join(attachDir.path, '${const Uuid().v4()}_$fileName');
    await file.copy(storedPath);

    final sha256Hex = sha256.convert(bytes).toString();

    final meta = AttachmentMeta(
      attachmentId: const Uuid().v4(),
      localPath: storedPath,
      fileName: fileName,
      mimeType: mimeType,
      sizeBytes: bytes.length,
      sha256Hex: sha256Hex,
      transferProgress: 0.0,
    );

    final msg = Message.createAttachment(
      conversationId: conversationId,
      senderId: _config.nodeId,
      recipientId: recipientId,
      attachment: meta,
    );

    await _db.insertMessage(msg);
    _messages = [..._messages, msg];
    notifyListeners();
    await _convsProvider.updateLastMessage(msg);

    final result = await _client.submitMessage(msg);
    if (!result.isOk) {
      await _db.updateMessageStatus(
        msg.messageId,
        DeliveryStatus.failed,
        failureReason: result.error,
      );
      final idx = _messages.indexWhere((m) => m.messageId == msg.messageId);
      if (idx != -1) {
        _messages[idx] = _messages[idx].copyWith(
          status: DeliveryStatus.failed,
          failureReason: result.error,
        );
        notifyListeners();
      }
    }
    return null; // success
  }

  // ── Retry ─────────────────────────────────────────────────────────────────

  Future<void> retryMessage(String messageId) async {
    final msg = await _db.getMessage(messageId);
    if (msg == null) return;
    if (msg.isExpired) {
      await _db.updateMessageStatus(messageId, DeliveryStatus.expired);
      return;
    }

    await _db.updateMessageStatus(messageId, DeliveryStatus.localQueued);
    final idx = _messages.indexWhere((m) => m.messageId == messageId);
    if (idx != -1) {
      _messages[idx] = _messages[idx].copyWith(
        status: DeliveryStatus.localQueued,
      );
      notifyListeners();
    }

    final result = await _client.submitMessage(msg);
    if (!result.isOk) {
      await _db.updateMessageStatus(
        messageId,
        DeliveryStatus.failed,
        failureReason: result.error,
      );
    }
  }

  // ── Incoming ──────────────────────────────────────────────────────────────

  /// Call periodically or on transport event to pull inbound messages.
  Future<void> pollIncoming() async {
    final result = await _client.receiveMessages();
    if (!result.isOk || result.value == null) return;
    for (final msg in result.value!) {
      final exists = await _db.messageExists(msg.messageId);
      if (exists) continue; // deduplicate
      await _db.insertMessage(msg);
      if (msg.conversationId == _currentConvId) {
        _messages = [..._messages, msg];
        notifyListeners();
      }
      await _convsProvider.updateLastMessage(msg);
    }
  }

  void close() {
    _eventSub?.cancel();
  }

  @override
  void dispose() {
    close();
    super.dispose();
  }
}
