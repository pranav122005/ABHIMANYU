// DTN Messenger — Conversation Model

import 'message.dart';

/// A bilateral conversation between the local user and one peer.
class Conversation {
  final String conversationId;
  final String peerId;
  final String peerName;
  final String? peerAvatar; // emoji or initials string, no external URLs
  final Message? lastMessage;
  final int unreadCount;
  final int updatedAtMs; // UTC ms

  const Conversation({
    required this.conversationId,
    required this.peerId,
    required this.peerName,
    this.peerAvatar,
    this.lastMessage,
    this.unreadCount = 0,
    required this.updatedAtMs,
  });

  factory Conversation.fromJson(Map<String, dynamic> j) => Conversation(
    conversationId: j['conversationId'] as String,
    peerId: j['peerId'] as String,
    peerName: j['peerName'] as String,
    peerAvatar: j['peerAvatar'] as String?,
    unreadCount: (j['unreadCount'] as int?) ?? 0,
    updatedAtMs: j['updatedAtMs'] as int,
  );

  Map<String, dynamic> toJson() => {
    'conversationId': conversationId,
    'peerId': peerId,
    'peerName': peerName,
    'peerAvatar': peerAvatar,
    'unreadCount': unreadCount,
    'updatedAtMs': updatedAtMs,
  };

  DateTime get updatedAt =>
      DateTime.fromMillisecondsSinceEpoch(updatedAtMs, isUtc: true).toLocal();

  Conversation copyWith({
    Message? lastMessage,
    int? unreadCount,
    int? updatedAtMs,
    String? peerName,
  }) => Conversation(
    conversationId: conversationId,
    peerId: peerId,
    peerName: peerName ?? this.peerName,
    peerAvatar: peerAvatar,
    lastMessage: lastMessage ?? this.lastMessage,
    unreadCount: unreadCount ?? this.unreadCount,
    updatedAtMs: updatedAtMs ?? this.updatedAtMs,
  );

  @override
  bool operator ==(Object other) =>
      other is Conversation && other.conversationId == conversationId;

  @override
  int get hashCode => conversationId.hashCode;
}
