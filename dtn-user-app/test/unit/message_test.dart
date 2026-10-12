// DTN Messenger — Unit Tests
// Tests: message model, serialization, IDs, validation, expiry, delivery states

import 'package:flutter_test/flutter_test.dart';
import 'package:dtn_messenger/core/models/message.dart';

void main() {
  // ─────────────────────────────────────────────────────────────────────────
  // Message ID uniqueness
  // ─────────────────────────────────────────────────────────────────────────

  group('Message ID generation', () {
    test('Two text messages have different IDs', () {
      final a = Message.createText(
        conversationId: 'conv-1',
        senderId: 'alice',
        recipientId: 'bob',
        text: 'Hello',
      );
      final b = Message.createText(
        conversationId: 'conv-1',
        senderId: 'alice',
        recipientId: 'bob',
        text: 'Hello',
      );
      expect(a.messageId, isNot(equals(b.messageId)));
    });

    test('Message ID is a non-empty string', () {
      final m = Message.createText(
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        text: 'hi',
      );
      expect(m.messageId, isNotEmpty);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Serialization round-trip
  // ─────────────────────────────────────────────────────────────────────────

  group('Message serialization', () {
    test('Text message round-trips through JSON', () {
      final m = Message.createText(
        conversationId: 'conv-abc',
        senderId: 'node-1',
        recipientId: 'node-2',
        text: 'Round-trip test',
        ttlSeconds: 3600,
      );
      final json = m.toJson();
      final restored = Message.fromJson(json);
      expect(restored.messageId, equals(m.messageId));
      expect(restored.conversationId, equals(m.conversationId));
      expect(restored.senderId, equals(m.senderId));
      expect(restored.recipientId, equals(m.recipientId));
      expect(restored.textContent, equals(m.textContent));
      expect(restored.type, equals(MessageType.text));
      expect(restored.status, equals(DeliveryStatus.localQueued));
      expect(restored.createdAtMs, equals(m.createdAtMs));
      expect(restored.expiresAtMs, equals(m.expiresAtMs));
    });

    test('Message with attachment round-trips', () {
      final att = AttachmentMeta(
        attachmentId: 'att-1',
        localPath: '/tmp/photo.jpg',
        fileName: 'photo.jpg',
        mimeType: 'image/jpeg',
        sizeBytes: 204800,
        sha256Hex: 'abc123',
      );
      final m = Message.createAttachment(
        conversationId: 'conv-x',
        senderId: 'alice',
        recipientId: 'bob',
        attachment: att,
      );
      final restored = Message.fromJson(m.toJson());
      expect(restored.type, equals(MessageType.image));
      expect(restored.attachment, isNotNull);
      expect(restored.attachment!.fileName, equals('photo.jpg'));
      expect(restored.attachment!.mimeType, equals('image/jpeg'));
      expect(restored.attachment!.sizeBytes, equals(204800));
      expect(restored.attachment!.sha256Hex, equals('abc123'));
    });

    test('Schema version is preserved', () {
      final m = Message.createText(
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        text: 't',
      );
      expect(m.toJson()['schemaVersion'], equals(kMessageSchemaVersion));
    });

    test('Relay path round-trips', () {
      final m = Message(
        messageId: 'id-1',
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        type: MessageType.text,
        createdAtMs: 1000000,
        expiresAtMs: 2000000,
        textContent: 'hi',
        relayPath: ['node-a', 'node-b', 'node-c'],
      );
      final restored = Message.fromJson(m.toJson());
      expect(restored.relayPath, equals(['node-a', 'node-b', 'node-c']));
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Delivery status serialization
  // ─────────────────────────────────────────────────────────────────────────

  group('DeliveryStatus serialization', () {
    for (final s in DeliveryStatus.values) {
      test('${s.name} round-trips', () {
        expect(DeliveryStatusX.fromJson(s.toJson()), equals(s));
      });
    }

    test('Unknown status defaults to localQueued', () {
      expect(
        DeliveryStatusX.fromJson('somethingUnknown'),
        equals(DeliveryStatus.localQueued),
      );
    });

    test('copyWith updates status and preserves other fields', () {
      final m = Message.createText(
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        text: 't',
      );
      final updated = m.copyWith(
        status: DeliveryStatus.peerTransferred,
        relayPath: ['relay-x'],
      );
      expect(updated.status, equals(DeliveryStatus.peerTransferred));
      expect(updated.relayPath, equals(['relay-x']));
      expect(updated.textContent, equals('t'));
      expect(updated.messageId, equals(m.messageId));
    });

    test('Peer transfer is NOT the same as final delivery', () {
      final m = Message.createText(
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        text: 't',
      );
      final transferred = m.copyWith(status: DeliveryStatus.peerTransferred);
      expect(
        transferred.status,
        isNot(equals(DeliveryStatus.destinationDelivered)),
      );
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Message expiry
  // ─────────────────────────────────────────────────────────────────────────

  group('Message expiry', () {
    test('Non-expired message is not expired', () {
      final m = Message.createText(
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        text: 'not expired',
        ttlSeconds: 3600,
      );
      expect(m.isExpired, isFalse);
    });

    test('Message with past expiry is expired', () {
      final past = DateTime.now().toUtc().millisecondsSinceEpoch - 1000;
      final m = Message(
        messageId: 'id-exp',
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        type: MessageType.text,
        createdAtMs: past - 5000,
        expiresAtMs: past,
        textContent: 'expired',
      );
      expect(m.isExpired, isTrue);
    });

    test('TTL is correctly applied to expiresAtMs', () {
      final before = DateTime.now().toUtc().millisecondsSinceEpoch;
      final m = Message.createText(
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        text: 't',
        ttlSeconds: 7 * 24 * 3600,
      );
      final after = DateTime.now().toUtc().millisecondsSinceEpoch;
      expect(
        m.expiresAtMs,
        greaterThanOrEqualTo(before + 7 * 24 * 3600 * 1000),
      );
      expect(
        m.expiresAtMs,
        lessThanOrEqualTo(after + 7 * 24 * 3600 * 1000 + 1000),
      );
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Attachment validation
  // ─────────────────────────────────────────────────────────────────────────

  group('Attachment validation', () {
    test('Valid JPEG accepted', () {
      expect(validateAttachment('image/jpeg', 1024), isNull);
    });

    test('Valid PNG accepted', () {
      expect(validateAttachment('image/png', 1024), isNull);
    });

    test('Valid WebP accepted', () {
      expect(validateAttachment('image/webp', 1024), isNull);
    });

    test('Valid MP3 accepted', () {
      expect(validateAttachment('audio/mpeg', 1024 * 1024), isNull);
    });

    test('Valid MP4 accepted', () {
      expect(validateAttachment('video/mp4', 5 * 1024 * 1024), isNull);
    });

    test('Unsupported type rejected', () {
      final err = validateAttachment('application/pdf', 1024);
      expect(err, isNotNull);
      expect(err, contains('not supported'));
    });

    test('Unsupported type GIF rejected', () {
      final err = validateAttachment('image/gif', 1024);
      expect(err, isNotNull);
    });

    test('Empty file rejected', () {
      final err = validateAttachment('image/jpeg', 0);
      expect(err, isNotNull);
      expect(err, contains('empty'));
    });

    test('Oversized file rejected with correct limit message', () {
      final err = validateAttachment(
        'image/jpeg',
        100 * 1024 * 1024,
        maxBytes: 50 * 1024 * 1024,
      );
      expect(err, isNotNull);
      expect(err, contains('50'));
    });

    test('File at exact limit is accepted', () {
      final limit = 50 * 1024 * 1024;
      expect(validateAttachment('image/png', limit, maxBytes: limit), isNull);
    });

    test('File 1 byte over limit is rejected', () {
      final limit = 50 * 1024 * 1024;
      expect(
        validateAttachment('image/png', limit + 1, maxBytes: limit),
        isNotNull,
      );
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Conversation ID
  // ─────────────────────────────────────────────────────────────────────────

  group('Conversation ID', () {
    test('Same pair produces same ID regardless of order', () {
      final id1 = buildConversationId('alice', 'bob');
      final id2 = buildConversationId('bob', 'alice');
      expect(id1, equals(id2));
    });

    test('Different pairs produce different IDs', () {
      final id1 = buildConversationId('alice', 'bob');
      final id2 = buildConversationId('alice', 'charlie');
      expect(id1, isNot(equals(id2)));
    });

    test('Conversation ID is 32 hex characters', () {
      final id = buildConversationId('x', 'y');
      expect(id.length, equals(32));
      expect(RegExp(r'^[0-9a-f]+$').hasMatch(id), isTrue);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Equality and deduplication
  // ─────────────────────────────────────────────────────────────────────────

  group('Message equality (deduplication)', () {
    test('Two messages with the same ID are equal', () {
      final m1 = Message(
        messageId: 'dup-id',
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        type: MessageType.text,
        createdAtMs: 0,
        expiresAtMs: 99999999999,
        textContent: 'hello',
      );
      final m2 = m1.copyWith(status: DeliveryStatus.peerTransferred);
      expect(m1, equals(m2));
      expect({m1, m2}.length, equals(1));
    });

    test('Two messages with different IDs are not equal', () {
      final m1 = Message.createText(
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        text: 'a',
      );
      final m2 = Message.createText(
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        text: 'a',
      );
      expect(m1, isNot(equals(m2)));
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // MessageType from MIME
  // ─────────────────────────────────────────────────────────────────────────

  group('MessageType from MIME', () {
    test('image/jpeg → image', () {
      final m = Message.createAttachment(
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        attachment: AttachmentMeta(
          attachmentId: 'a',
          localPath: '/f.jpg',
          fileName: 'f.jpg',
          mimeType: 'image/jpeg',
          sizeBytes: 100,
          sha256Hex: 'abc',
        ),
      );
      expect(m.type, equals(MessageType.image));
    });

    test('audio/mpeg → audio', () {
      final m = Message.createAttachment(
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        attachment: AttachmentMeta(
          attachmentId: 'a',
          localPath: '/f.mp3',
          fileName: 'f.mp3',
          mimeType: 'audio/mpeg',
          sizeBytes: 100,
          sha256Hex: 'abc',
        ),
      );
      expect(m.type, equals(MessageType.audio));
    });

    test('video/mp4 → video', () {
      final m = Message.createAttachment(
        conversationId: 'c',
        senderId: 's',
        recipientId: 'r',
        attachment: AttachmentMeta(
          attachmentId: 'a',
          localPath: '/f.mp4',
          fileName: 'f.mp4',
          mimeType: 'video/mp4',
          sizeBytes: 100,
          sha256Hex: 'abc',
        ),
      );
      expect(m.type, equals(MessageType.video));
    });
  });
}
