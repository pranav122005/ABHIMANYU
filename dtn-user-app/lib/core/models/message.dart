// DTN Messenger — Message Model
// Versioned, documented data model for DTN messages and attachments.
// All timestamps are stored as UTC milliseconds since epoch.

import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:uuid/uuid.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Enumerations
// ─────────────────────────────────────────────────────────────────────────────

/// DTN delivery lifecycle states.
/// LOCAL_QUEUED  → persisted locally, awaiting peer transfer.
/// PEER_TRANSFERRED → accepted by an immediate relay/peer.
/// DESTINATION_DELIVERED → final recipient confirmed acceptance.
/// FAILED → a defined, reported failure occurred.
/// EXPIRED → the message's TTL elapsed before delivery.
enum DeliveryStatus {
  localQueued,
  peerTransferred,
  destinationDelivered,
  failed,
  expired,
}

extension DeliveryStatusX on DeliveryStatus {
  String toJson() => name;

  static DeliveryStatus fromJson(String s) => DeliveryStatus.values.firstWhere(
    (e) => e.name == s,
    orElse: () => DeliveryStatus.localQueued,
  );

  String get displayLabel {
    switch (this) {
      case DeliveryStatus.localQueued:
        return 'Queued';
      case DeliveryStatus.peerTransferred:
        return 'Transferred';
      case DeliveryStatus.destinationDelivered:
        return 'Delivered';
      case DeliveryStatus.failed:
        return 'Failed';
      case DeliveryStatus.expired:
        return 'Expired';
    }
  }
}

/// Type of message payload.
enum MessageType { text, image, audio, video }

extension MessageTypeX on MessageType {
  String toJson() => name;

  static MessageType fromJson(String s) => MessageType.values.firstWhere(
    (e) => e.name == s,
    orElse: () => MessageType.text,
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Attachment Metadata
// ─────────────────────────────────────────────────────────────────────────────

class AttachmentMeta {
  final String attachmentId;
  final String localPath;
  final String fileName;
  final String mimeType;
  final int sizeBytes;
  final String sha256Hex;
  final double? transferProgress;
  final bool isComplete;

  const AttachmentMeta({
    required this.attachmentId,
    required this.localPath,
    required this.fileName,
    required this.mimeType,
    required this.sizeBytes,
    required this.sha256Hex,
    this.transferProgress,
    this.isComplete = false,
  });

  factory AttachmentMeta.fromJson(Map<String, dynamic> j) => AttachmentMeta(
    attachmentId: j['attachmentId'] as String,
    localPath: j['localPath'] as String,
    fileName: j['fileName'] as String,
    mimeType: j['mimeType'] as String,
    sizeBytes: j['sizeBytes'] as int,
    sha256Hex: j['sha256Hex'] as String,
    transferProgress: (j['transferProgress'] as num?)?.toDouble(),
    isComplete: (j['isComplete'] as bool?) ?? false,
  );

  Map<String, dynamic> toJson() => {
    'attachmentId': attachmentId,
    'localPath': localPath,
    'fileName': fileName,
    'mimeType': mimeType,
    'sizeBytes': sizeBytes,
    'sha256Hex': sha256Hex,
    'transferProgress': transferProgress,
    'isComplete': isComplete,
  };

  AttachmentMeta copyWith({
    double? transferProgress,
    bool? isComplete,
    String? localPath,
  }) => AttachmentMeta(
    attachmentId: attachmentId,
    localPath: localPath ?? this.localPath,
    fileName: fileName,
    mimeType: mimeType,
    sizeBytes: sizeBytes,
    sha256Hex: sha256Hex,
    transferProgress: transferProgress ?? this.transferProgress,
    isComplete: isComplete ?? this.isComplete,
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Message
// ─────────────────────────────────────────────────────────────────────────────

const int kMessageSchemaVersion = 1;
const int kDefaultMaxAttachmentBytes = 50 * 1024 * 1024; // 50 MB

class Message {
  final int schemaVersion;
  final String messageId;
  final String conversationId;
  final String senderId;
  final String recipientId;
  final MessageType type;
  final int createdAtMs; // UTC ms since epoch
  final int expiresAtMs; // UTC ms since epoch
  final String? textContent;
  final AttachmentMeta? attachment;
  final DeliveryStatus status;
  final bool isMine;
  final String? failureReason;
  final List<String> relayPath;

  const Message({
    this.schemaVersion = kMessageSchemaVersion,
    required this.messageId,
    required this.conversationId,
    required this.senderId,
    required this.recipientId,
    required this.type,
    required this.createdAtMs,
    required this.expiresAtMs,
    this.textContent,
    this.attachment,
    this.status = DeliveryStatus.localQueued,
    this.isMine = true,
    this.failureReason,
    this.relayPath = const [],
  });

  factory Message.createText({
    required String conversationId,
    required String senderId,
    required String recipientId,
    required String text,
    int ttlSeconds = 7 * 24 * 3600,
  }) {
    final now = DateTime.now().toUtc().millisecondsSinceEpoch;
    return Message(
      messageId: const Uuid().v4(),
      conversationId: conversationId,
      senderId: senderId,
      recipientId: recipientId,
      type: MessageType.text,
      createdAtMs: now,
      expiresAtMs: now + ttlSeconds * 1000,
      textContent: text,
    );
  }

  factory Message.createAttachment({
    required String conversationId,
    required String senderId,
    required String recipientId,
    required AttachmentMeta attachment,
    int ttlSeconds = 7 * 24 * 3600,
  }) {
    final now = DateTime.now().toUtc().millisecondsSinceEpoch;
    return Message(
      messageId: const Uuid().v4(),
      conversationId: conversationId,
      senderId: senderId,
      recipientId: recipientId,
      type: _typeFromMime(attachment.mimeType),
      createdAtMs: now,
      expiresAtMs: now + ttlSeconds * 1000,
      attachment: attachment,
    );
  }

  factory Message.fromJson(Map<String, dynamic> j) => Message(
    schemaVersion: (j['schemaVersion'] as int?) ?? kMessageSchemaVersion,
    messageId: j['messageId'] as String,
    conversationId: j['conversationId'] as String,
    senderId: j['senderId'] as String,
    recipientId: j['recipientId'] as String,
    type: MessageTypeX.fromJson(j['type'] as String),
    createdAtMs: j['createdAtMs'] as int,
    expiresAtMs: j['expiresAtMs'] as int,
    textContent: j['textContent'] as String?,
    attachment: j['attachment'] != null
        ? AttachmentMeta.fromJson(j['attachment'] as Map<String, dynamic>)
        : null,
    status: DeliveryStatusX.fromJson(j['status'] as String),
    isMine: (j['isMine'] as bool?) ?? false,
    failureReason: j['failureReason'] as String?,
    relayPath: (j['relayPath'] as List<dynamic>?)?.cast<String>() ?? const [],
  );

  Map<String, dynamic> toJson() => {
    'schemaVersion': schemaVersion,
    'messageId': messageId,
    'conversationId': conversationId,
    'senderId': senderId,
    'recipientId': recipientId,
    'type': type.toJson(),
    'createdAtMs': createdAtMs,
    'expiresAtMs': expiresAtMs,
    'textContent': textContent,
    'attachment': attachment?.toJson(),
    'status': status.toJson(),
    'isMine': isMine,
    'failureReason': failureReason,
    'relayPath': relayPath,
  };

  bool get isExpired =>
      DateTime.now().toUtc().millisecondsSinceEpoch >= expiresAtMs;

  DateTime get createdAt =>
      DateTime.fromMillisecondsSinceEpoch(createdAtMs, isUtc: true).toLocal();

  DateTime get expiresAt =>
      DateTime.fromMillisecondsSinceEpoch(expiresAtMs, isUtc: true).toLocal();

  Message copyWith({
    DeliveryStatus? status,
    String? failureReason,
    List<String>? relayPath,
    AttachmentMeta? attachment,
  }) => Message(
    schemaVersion: schemaVersion,
    messageId: messageId,
    conversationId: conversationId,
    senderId: senderId,
    recipientId: recipientId,
    type: type,
    createdAtMs: createdAtMs,
    expiresAtMs: expiresAtMs,
    textContent: textContent,
    attachment: attachment ?? this.attachment,
    status: status ?? this.status,
    isMine: isMine,
    failureReason: failureReason ?? this.failureReason,
    relayPath: relayPath ?? this.relayPath,
  );

  @override
  bool operator ==(Object other) =>
      other is Message && other.messageId == messageId;

  @override
  int get hashCode => messageId.hashCode;

  static MessageType _typeFromMime(String mime) {
    if (mime.startsWith('image/')) return MessageType.image;
    if (mime.startsWith('audio/')) return MessageType.audio;
    if (mime.startsWith('video/')) return MessageType.video;
    return MessageType.text;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Allowed attachment types & validation
// ─────────────────────────────────────────────────────────────────────────────

const Set<String> kAllowedMimeTypes = {
  'image/jpeg',
  'image/png',
  'image/webp',
  'audio/mpeg',
  'audio/mp3',
  'video/mp4',
};

String? validateAttachment(
  String mimeType,
  int sizeBytes, {
  int maxBytes = kDefaultMaxAttachmentBytes,
}) {
  if (!kAllowedMimeTypes.contains(mimeType.toLowerCase())) {
    return 'File type "$mimeType" is not supported. '
        'Allowed types: JPEG, PNG, WebP images · MP3 audio · MP4 video.';
  }
  if (sizeBytes == 0) return 'File is empty.';
  if (sizeBytes > maxBytes) {
    final mb = (maxBytes / (1024 * 1024)).toStringAsFixed(0);
    final actual = (sizeBytes / (1024 * 1024)).toStringAsFixed(1);
    return 'File is too large ($actual MB). Maximum: $mb MB.';
  }
  return null;
}

/// Build a stable, order-independent conversation ID from two peer IDs.
String buildConversationId(String a, String b) {
  final sorted = [a, b]..sort();
  final combined = '${sorted[0]}:${sorted[1]}';
  final digest = sha256.convert(utf8.encode(combined));
  return digest.toString().substring(0, 32);
}
