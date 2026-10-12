// DTN Messenger — SQLite Persistence Layer
// Uses sqflite on Android and sqflite_common_ffi on Windows.

import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import '../models/message.dart';
import '../models/conversation.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Schema DDL
// ─────────────────────────────────────────────────────────────────────────────

const _ddlMessages = '''
CREATE TABLE IF NOT EXISTS messages (
  message_id      TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  sender_id       TEXT NOT NULL,
  recipient_id    TEXT NOT NULL,
  type            TEXT NOT NULL,
  created_at_ms   INTEGER NOT NULL,
  expires_at_ms   INTEGER NOT NULL,
  text_content    TEXT,
  attachment_json TEXT,
  status          TEXT NOT NULL DEFAULT 'localQueued',
  is_mine         INTEGER NOT NULL DEFAULT 1,
  failure_reason  TEXT,
  relay_path_json TEXT NOT NULL DEFAULT '[]',
  schema_version  INTEGER NOT NULL DEFAULT 1
)
''';

const _ddlConversations = '''
CREATE TABLE IF NOT EXISTS conversations (
  conversation_id TEXT PRIMARY KEY,
  peer_id         TEXT NOT NULL,
  peer_name       TEXT NOT NULL,
  peer_avatar     TEXT,
  unread_count    INTEGER NOT NULL DEFAULT 0,
  updated_at_ms   INTEGER NOT NULL
)
''';

const _ddlIndexes = [
  'CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, created_at_ms)',
  'CREATE INDEX IF NOT EXISTS idx_msg_status ON messages(status)',
  'CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at_ms DESC)',
];

// ─────────────────────────────────────────────────────────────────────────────
// AppDatabase
// ─────────────────────────────────────────────────────────────────────────────

class AppDatabase {
  static const _dbName = 'dtn_messenger.db';
  static const _dbVersion = 1;

  late Database _db;

  AppDatabase._();

  static Future<AppDatabase> open() async {
    final instance = AppDatabase._();
    await instance._init();
    return instance;
  }

  Future<void> _init() async {
    if (Platform.isWindows || Platform.isLinux) {
      sqfliteFfiInit();
      databaseFactory = databaseFactoryFfi;
    }

    final dir = await getApplicationDocumentsDirectory();
    final dbPath = p.join(dir.path, 'DTNMessenger', _dbName);

    // Ensure directory exists.
    await Directory(p.dirname(dbPath)).create(recursive: true);

    _db = await openDatabase(
      dbPath,
      version: _dbVersion,
      onCreate: _onCreate,
      onUpgrade: _onUpgrade,
    );
  }

  Future<void> _onCreate(Database db, int version) async {
    await db.execute(_ddlMessages);
    await db.execute(_ddlConversations);
    for (final idx in _ddlIndexes) {
      await db.execute(idx);
    }
  }

  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
    // Future migrations go here.
    await _onCreate(db, newVersion);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Message operations
  // ─────────────────────────────────────────────────────────────────────────

  Future<void> insertMessage(Message msg) async {
    await _db.insert(
      'messages',
      _messageToRow(msg),
      conflictAlgorithm: ConflictAlgorithm.ignore, // idempotent
    );
  }

  Future<void> upsertMessage(Message msg) async {
    await _db.insert(
      'messages',
      _messageToRow(msg),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> updateMessageStatus(
    String messageId,
    DeliveryStatus status, {
    String? failureReason,
    List<String>? relayPath,
  }) async {
    final values = <String, Object?>{
      'status': status.toJson(),
      'failure_reason': failureReason,
    };
    if (relayPath != null) {
      values['relay_path_json'] = jsonEncode(relayPath);
    }
    await _db.update(
      'messages',
      values,
      where: 'message_id = ?',
      whereArgs: [messageId],
    );
  }

  Future<void> updateAttachmentProgress(
    String messageId,
    double progress,
    bool isComplete,
  ) async {
    final row = await _db.query(
      'messages',
      columns: ['attachment_json'],
      where: 'message_id = ?',
      whereArgs: [messageId],
    );
    if (row.isEmpty || row.first['attachment_json'] == null) return;

    final json = jsonDecode(
      row.first['attachment_json'] as String,
    ) as Map<String, dynamic>;
    json['transferProgress'] = progress;
    json['isComplete'] = isComplete;
    await _db.update(
      'messages',
      {'attachment_json': jsonEncode(json)},
      where: 'message_id = ?',
      whereArgs: [messageId],
    );
  }

  Future<List<Message>> getMessages(
    String conversationId, {
    int limit = 200,
    int offset = 0,
  }) async {
    final rows = await _db.query(
      'messages',
      where: 'conversation_id = ?',
      whereArgs: [conversationId],
      orderBy: 'created_at_ms ASC',
      limit: limit,
      offset: offset,
    );
    return rows.map(_messageFromRow).toList();
  }

  Future<Message?> getMessage(String messageId) async {
    final rows = await _db.query(
      'messages',
      where: 'message_id = ?',
      whereArgs: [messageId],
    );
    if (rows.isEmpty) return null;
    return _messageFromRow(rows.first);
  }

  Future<List<Message>> getOutboxMessages() async {
    final rows = await _db.query(
      'messages',
      where: 'status IN (?, ?) AND is_mine = 1',
      whereArgs: [
        DeliveryStatus.localQueued.toJson(),
        DeliveryStatus.peerTransferred.toJson(),
      ],
      orderBy: 'created_at_ms ASC',
    );
    return rows.map(_messageFromRow).toList();
  }

  Future<bool> messageExists(String messageId) async {
    final rows = await _db.query(
      'messages',
      columns: ['message_id'],
      where: 'message_id = ?',
      whereArgs: [messageId],
      limit: 1,
    );
    return rows.isNotEmpty;
  }

  Future<void> markExpiredMessages() async {
    final nowMs = DateTime.now().toUtc().millisecondsSinceEpoch;
    await _db.update(
      'messages',
      {'status': DeliveryStatus.expired.toJson()},
      where: "expires_at_ms <= ? AND status IN (?, ?)",
      whereArgs: [
        nowMs,
        DeliveryStatus.localQueued.toJson(),
        DeliveryStatus.peerTransferred.toJson(),
      ],
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Conversation operations
  // ─────────────────────────────────────────────────────────────────────────

  Future<void> upsertConversation(Conversation conv) async {
    await _db.insert(
      'conversations',
      _convToRow(conv),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<List<Conversation>> getConversations() async {
    final rows = await _db.query(
      'conversations',
      orderBy: 'updated_at_ms DESC',
    );
    final convs = <Conversation>[];
    for (final row in rows) {
      final conv = _convFromRow(row);
      // Fetch last message for preview.
      final msgs = await getMessages(
        conv.conversationId,
        limit: 1,
        offset: await _getMessageCount(conv.conversationId) - 1,
      );
      if (msgs.isNotEmpty) {
        convs.add(conv.copyWith(lastMessage: msgs.last));
      } else {
        convs.add(conv);
      }
    }
    return convs;
  }

  Future<Conversation?> getConversation(String convId) async {
    final rows = await _db.query(
      'conversations',
      where: 'conversation_id = ?',
      whereArgs: [convId],
    );
    if (rows.isEmpty) return null;
    return _convFromRow(rows.first);
  }

  Future<void> incrementUnread(String conversationId) async {
    await _db.rawUpdate(
      'UPDATE conversations SET unread_count = unread_count + 1 WHERE conversation_id = ?',
      [conversationId],
    );
  }

  Future<void> markRead(String conversationId) async {
    await _db.update(
      'conversations',
      {'unread_count': 0},
      where: 'conversation_id = ?',
      whereArgs: [conversationId],
    );
  }

  Future<int> _getMessageCount(String conversationId) async {
    final result = await _db.rawQuery(
      'SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = ?',
      [conversationId],
    );
    return (result.first['cnt'] as int?) ?? 0;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Diagnostics
  // ─────────────────────────────────────────────────────────────────────────

  Future<Map<String, int>> getStorageStats() async {
    final msgCount = await _db.rawQuery('SELECT COUNT(*) as c FROM messages');
    final convCount = await _db.rawQuery(
      'SELECT COUNT(*) as c FROM conversations',
    );
    return {
      'messages': (msgCount.first['c'] as int?) ?? 0,
      'conversations': (convCount.first['c'] as int?) ?? 0,
    };
  }

  Future<void> close() async => _db.close();

  // ─────────────────────────────────────────────────────────────────────────
  // Row ↔ model mapping
  // ─────────────────────────────────────────────────────────────────────────

  Map<String, Object?> _messageToRow(Message m) => {
    'message_id': m.messageId,
    'conversation_id': m.conversationId,
    'sender_id': m.senderId,
    'recipient_id': m.recipientId,
    'type': m.type.toJson(),
    'created_at_ms': m.createdAtMs,
    'expires_at_ms': m.expiresAtMs,
    'text_content': m.textContent,
    'attachment_json': m.attachment != null
        ? jsonEncode(m.attachment!.toJson())
        : null,
    'status': m.status.toJson(),
    'is_mine': m.isMine ? 1 : 0,
    'failure_reason': m.failureReason,
    'relay_path_json': jsonEncode(m.relayPath),
    'schema_version': m.schemaVersion,
  };

  Message _messageFromRow(Map<String, Object?> row) => Message(
    schemaVersion: (row['schema_version'] as int?) ?? kMessageSchemaVersion,
    messageId: row['message_id'] as String,
    conversationId: row['conversation_id'] as String,
    senderId: row['sender_id'] as String,
    recipientId: row['recipient_id'] as String,
    type: MessageTypeX.fromJson(row['type'] as String),
    createdAtMs: row['created_at_ms'] as int,
    expiresAtMs: row['expires_at_ms'] as int,
    textContent: row['text_content'] as String?,
    attachment: row['attachment_json'] != null
        ? AttachmentMeta.fromJson(
            jsonDecode(row['attachment_json'] as String)
                as Map<String, dynamic>,
          )
        : null,
    status: DeliveryStatusX.fromJson(row['status'] as String),
    isMine: (row['is_mine'] as int) == 1,
    failureReason: row['failure_reason'] as String?,
    relayPath: (jsonDecode(row['relay_path_json'] as String) as List)
        .cast<String>(),
  );

  Map<String, Object?> _convToRow(Conversation c) => {
    'conversation_id': c.conversationId,
    'peer_id': c.peerId,
    'peer_name': c.peerName,
    'peer_avatar': c.peerAvatar,
    'unread_count': c.unreadCount,
    'updated_at_ms': c.updatedAtMs,
  };

  Conversation _convFromRow(Map<String, Object?> row) => Conversation(
    conversationId: row['conversation_id'] as String,
    peerId: row['peer_id'] as String,
    peerName: row['peer_name'] as String,
    peerAvatar: row['peer_avatar'] as String?,
    unreadCount: (row['unread_count'] as int?) ?? 0,
    updatedAtMs: row['updated_at_ms'] as int,
  );
}
