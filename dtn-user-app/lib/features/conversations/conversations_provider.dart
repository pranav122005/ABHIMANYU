// DTN Messenger — Conversations Provider

import 'package:flutter/foundation.dart';

import '../../core/models/conversation.dart';
import '../../core/models/message.dart';
import '../../core/persistence/app_database.dart';

class ConversationsProvider extends ChangeNotifier {
  final AppDatabase _db;

  ConversationsProvider(this._db);

  List<Conversation> _conversations = [];
  bool _loading = false;
  String? _error;

  List<Conversation> get conversations => _conversations;
  bool get loading => _loading;
  String? get error => _error;

  Future<void> loadConversations() async {
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      _conversations = await _db.getConversations();
    } catch (e) {
      _error = 'Failed to load conversations: $e';
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<Conversation> ensureConversation({
    required String conversationId,
    required String peerId,
    required String peerName,
    String? peerAvatar,
  }) async {
    final existing = _conversations.cast<Conversation?>().firstWhere(
      (c) => c!.conversationId == conversationId,
      orElse: () => null,
    );
    if (existing != null) return existing;

    final conv = Conversation(
      conversationId: conversationId,
      peerId: peerId,
      peerName: peerName,
      peerAvatar: peerAvatar,
      updatedAtMs: DateTime.now().toUtc().millisecondsSinceEpoch,
    );
    await _db.upsertConversation(conv);
    _conversations = [conv, ..._conversations];
    notifyListeners();
    return conv;
  }

  Future<void> updateLastMessage(Message msg) async {
    final idx = _conversations.indexWhere(
      (c) => c.conversationId == msg.conversationId,
    );
    if (idx == -1) return;

    final updated = _conversations[idx].copyWith(
      lastMessage: msg,
      updatedAtMs: msg.createdAtMs,
    );
    _conversations[idx] = updated;
    await _db.upsertConversation(updated);
    // Keep sorted by updated time.
    _conversations.sort((a, b) => b.updatedAtMs.compareTo(a.updatedAtMs));
    notifyListeners();
  }

  Future<void> markRead(String conversationId) async {
    await _db.markRead(conversationId);
    final idx = _conversations.indexWhere(
      (c) => c.conversationId == conversationId,
    );
    if (idx != -1) {
      _conversations[idx] = _conversations[idx].copyWith(unreadCount: 0);
      notifyListeners();
    }
  }

  List<Conversation> search(String query) {
    if (query.isEmpty) return _conversations;
    final q = query.toLowerCase();
    return _conversations
        .where(
          (c) =>
              c.peerName.toLowerCase().contains(q) ||
              (c.lastMessage?.textContent?.toLowerCase().contains(q) ?? false),
        )
        .toList();
  }
}
