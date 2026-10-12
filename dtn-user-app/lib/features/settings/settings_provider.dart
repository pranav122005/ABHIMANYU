// DTN Messenger — Settings Provider

import 'package:flutter/material.dart';

import '../../core/models/app_config.dart';
import '../../core/persistence/app_database.dart';

class SettingsProvider extends ChangeNotifier {
  final AppConfig _config;
  final AppDatabase _db;

  SettingsProvider(this._config, this._db);

  AppConfig get config => _config;

  ThemeMode get themeMode {
    switch (_config.themeMode) {
      case 'light':
        return ThemeMode.light;
      case 'dark':
        return ThemeMode.dark;
      default:
        return ThemeMode.system;
    }
  }

  Future<void> setDisplayName(String name) async {
    await _config.setDisplayName(name);
    notifyListeners();
  }

  Future<void> setEndpointUrl(String? url) async {
    await _config.setEndpointUrl(url);
    notifyListeners();
  }

  Future<void> setSimulationMode(bool v) async {
    await _config.setSimulationMode(v);
    notifyListeners();
  }

  Future<void> setThemeMode(String mode) async {
    await _config.setThemeMode(mode);
    notifyListeners();
  }

  Future<Map<String, dynamic>> getStorageStats() async {
    return await _db.getStorageStats();
  }
}
