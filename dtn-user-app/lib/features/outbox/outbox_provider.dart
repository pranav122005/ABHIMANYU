// DTN Messenger — Outbox Provider

import 'package:flutter/foundation.dart';

import '../../core/models/message.dart';
import '../../core/persistence/app_database.dart';
import '../../core/transport/dtn_client.dart';

class OutboxProvider extends ChangeNotifier {
  final AppDatabase _db;
  final DtnClient _client;

  OutboxProvider(this._db, this._client);

  List<Message> _outbox = [];
  bool _loading = false;

  List<Message> get outbox => _outbox;
  bool get loading => _loading;

  List<Message> get queued =>
      _outbox.where((m) => m.status == DeliveryStatus.localQueued).toList();
  List<Message> get inTransit =>
      _outbox.where((m) => m.status == DeliveryStatus.peerTransferred).toList();
  List<Message> get delivered => _outbox
      .where((m) => m.status == DeliveryStatus.destinationDelivered)
      .toList();
  List<Message> get failed =>
      _outbox.where((m) => m.status == DeliveryStatus.failed).toList();
  List<Message> get expired =>
      _outbox.where((m) => m.status == DeliveryStatus.expired).toList();

  Future<void> load() async {
    _loading = true;
    notifyListeners();
    await _db.markExpiredMessages();
    _outbox = await _db.getOutboxMessages();
    _loading = false;
    notifyListeners();
  }

  Future<void> retry(String messageId) async {
    final msg = await _db.getMessage(messageId);
    if (msg == null) return;
    if (msg.isExpired) {
      await _db.updateMessageStatus(messageId, DeliveryStatus.expired);
      await load();
      return;
    }
    await _db.updateMessageStatus(messageId, DeliveryStatus.localQueued);
    final result = await _client.submitMessage(msg);
    if (!result.isOk) {
      await _db.updateMessageStatus(
        messageId,
        DeliveryStatus.failed,
        failureReason: result.error,
      );
    }
    await load();
  }

  void onDeliveryEvent(DeliveryEvent event) {
    final idx = _outbox.indexWhere((m) => m.messageId == event.messageId);
    if (idx != -1) {
      _outbox[idx] = _outbox[idx].copyWith(
        status: event.newStatus,
        failureReason: event.failureReason,
      );
      notifyListeners();
    }
  }
}
