// DTN Messenger — Local User Identity & Configuration

import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

/// The identity of the local user/device node.
class LocalIdentity {
  final String nodeId;
  final String displayName;
  final String? avatarEmoji;

  const LocalIdentity({
    required this.nodeId,
    required this.displayName,
    this.avatarEmoji,
  });
}

/// Manages persisted user identity and app configuration.
class AppConfig {
  static const _kNodeId = 'dtn_node_id';
  static const _kDisplayName = 'dtn_display_name';
  static const _kAvatarEmoji = 'dtn_avatar_emoji';
  static const _kEndpointUrl = 'dtn_endpoint_url';
  static const _kSimMode = 'dtn_sim_mode';
  static const _kMaxAttachmentMb = 'dtn_max_attachment_mb';
  static const _kThemeMode = 'dtn_theme_mode';

  final SharedPreferences _prefs;

  AppConfig._(this._prefs);

  static Future<AppConfig> load() async {
    final prefs = await SharedPreferences.getInstance();
    final config = AppConfig._(prefs);
    // Ensure node ID is initialised on first run.
    if (prefs.getString(_kNodeId) == null) {
      await prefs.setString(_kNodeId, const Uuid().v4());
    }
    return config;
  }

  // ── Node identity ─────────────────────────────────────────────────────────

  String get nodeId => _prefs.getString(_kNodeId)!;

  String get displayName => _prefs.getString(_kDisplayName) ?? 'DTN User';

  Future<void> setDisplayName(String name) =>
      _prefs.setString(_kDisplayName, name.trim());

  String? get avatarEmoji => _prefs.getString(_kAvatarEmoji);
  Future<void> setAvatarEmoji(String e) => _prefs.setString(_kAvatarEmoji, e);

  LocalIdentity get identity => LocalIdentity(
    nodeId: nodeId,
    displayName: displayName,
    avatarEmoji: avatarEmoji,
  );

  // ── Transport ─────────────────────────────────────────────────────────────

  /// HTTP endpoint of the DTN gateway (e.g., http://192.168.1.10:8765).
  /// null → use the development simulation adapter.
  String? get endpointUrl => _prefs.getString(_kEndpointUrl);
  Future<void> setEndpointUrl(String? url) async {
    if (url == null || url.trim().isEmpty) {
      await _prefs.remove(_kEndpointUrl);
    } else {
      await _prefs.setString(_kEndpointUrl, url.trim());
    }
  }

  /// Force simulation mode even when an endpoint URL is configured.
  bool get simulationMode => _prefs.getBool(_kSimMode) ?? true;
  Future<void> setSimulationMode(bool v) => _prefs.setBool(_kSimMode, v);

  /// Whether the app is using real or simulated connectivity.
  bool get isSimulated => simulationMode || endpointUrl == null;

  // ── Limits ────────────────────────────────────────────────────────────────

  int get maxAttachmentMb => _prefs.getInt(_kMaxAttachmentMb) ?? 50;
  int get maxAttachmentBytes => maxAttachmentMb * 1024 * 1024;
  Future<void> setMaxAttachmentMb(int mb) =>
      _prefs.setInt(_kMaxAttachmentMb, mb);

  // ── Theme ─────────────────────────────────────────────────────────────────

  /// 'system' | 'light' | 'dark'
  String get themeMode => _prefs.getString(_kThemeMode) ?? 'system';
  Future<void> setThemeMode(String mode) => _prefs.setString(_kThemeMode, mode);
}
