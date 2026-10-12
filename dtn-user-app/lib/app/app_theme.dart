// DTN Messenger — App Theme

import 'package:flutter/material.dart';

class AppTheme {
  static const _primaryColor = Color(0xFF00B4D8); // Teal-blue — DTN brand

  // ── Shared text theme ─────────────────────────────────────────────────────

  static TextTheme get _textTheme => const TextTheme(
    headlineLarge: TextStyle(fontWeight: FontWeight.w700),
    headlineMedium: TextStyle(fontWeight: FontWeight.w700),
    titleLarge: TextStyle(fontWeight: FontWeight.w600),
    titleMedium: TextStyle(fontWeight: FontWeight.w500),
    bodyLarge: TextStyle(fontSize: 16),
    bodyMedium: TextStyle(fontSize: 14),
    bodySmall: TextStyle(fontSize: 12),
    labelSmall: TextStyle(fontSize: 11),
  );

  // ── Light theme ───────────────────────────────────────────────────────────

  static ThemeData get light => ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: _primaryColor,
      brightness: Brightness.light,
    ),
    textTheme: _textTheme,
    appBarTheme: const AppBarTheme(
      elevation: 0,
      centerTitle: false,
      backgroundColor: Colors.white,
      foregroundColor: Colors.black87,
      surfaceTintColor: Colors.transparent,
    ),
    inputDecorationTheme: InputDecorationTheme(
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(24),
        borderSide: BorderSide.none,
      ),
      filled: true,
      fillColor: const Color(0xFFF0F2F5),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: _primaryColor,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: Color(0xFFE0E0E0)),
      ),
    ),
    dividerTheme: const DividerThemeData(space: 0),
  );

  // ── Dark theme ────────────────────────────────────────────────────────────

  static ThemeData get dark => ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: _primaryColor,
      brightness: Brightness.dark,
    ),
    textTheme: _textTheme,
    appBarTheme: AppBarTheme(
      elevation: 0,
      centerTitle: false,
      backgroundColor: const Color(0xFF1C1C1E),
      foregroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
    ),
    scaffoldBackgroundColor: const Color(0xFF121212),
    inputDecorationTheme: InputDecorationTheme(
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(24),
        borderSide: BorderSide.none,
      ),
      filled: true,
      fillColor: const Color(0xFF2C2C2E),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: _primaryColor,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: const Color(0xFF1C1C1E),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: Color(0xFF3A3A3C)),
      ),
    ),
    dividerTheme: const DividerThemeData(space: 0),
  );

  // ── Chat bubble colors ────────────────────────────────────────────────────

  static Color sentBubbleColor(BuildContext ctx) =>
      Theme.of(ctx).colorScheme.primary;

  static Color receivedBubbleColor(BuildContext ctx) =>
      Theme.of(ctx).brightness == Brightness.dark
      ? const Color(0xFF2C2C2E)
      : const Color(0xFFE8E8E8);

  static Color sentTextColor(BuildContext ctx) =>
      Theme.of(ctx).colorScheme.onPrimary;

  static Color receivedTextColor(BuildContext ctx) =>
      Theme.of(ctx).brightness == Brightness.dark
      ? Colors.white
      : Colors.black87;
}
