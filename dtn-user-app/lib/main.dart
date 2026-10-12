// DTN Messenger — App Root (main.dart)

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/models/app_config.dart';
import 'core/persistence/app_database.dart';
import 'core/transport/dtn_client.dart';
import 'core/transport/simulated_dtn_client.dart';
import 'features/conversations/conversations_provider.dart';
import 'features/chat/chat_provider.dart';
import 'features/nearby/nearby_provider.dart';
import 'features/outbox/outbox_provider.dart';
import 'features/settings/settings_provider.dart';
import 'features/conversations/conversations_screen.dart';
import 'app/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final config = await AppConfig.load();
  final db = await AppDatabase.open();

  // Choose transport: real endpoint or simulation.
  final DtnClient client = SimulatedDtnClient();

  runApp(
    MultiProvider(
      providers: [
        // Singletons
        Provider<AppConfig>.value(value: config),
        Provider<AppDatabase>.value(value: db),
        Provider<DtnClient>.value(value: client),

        // Feature providers
        ChangeNotifierProvider(create: (_) => ConversationsProvider(db)),
        ChangeNotifierProvider(create: (_) => NearbyProvider(client)),
        ChangeNotifierProvider(create: (_) => OutboxProvider(db, client)),
        ChangeNotifierProvider(create: (_) => SettingsProvider(config, db)),

        // ChatProvider needs several deps — use ProxyProvider to wire them.
        ChangeNotifierProxyProvider<ConversationsProvider, ChatProvider>(
          create: (ctx) => ChatProvider(
            db,
            client,
            config,
            ctx.read<ConversationsProvider>(),
          ),
          update: (ctx, convsProv, prev) =>
              prev ?? ChatProvider(db, client, config, convsProv),
        ),
      ],
      child: const DtnMessengerApp(),
    ),
  );
}

class DtnMessengerApp extends StatelessWidget {
  const DtnMessengerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<SettingsProvider>(
      builder: (_, settings, __) {
        return MaterialApp(
          title: 'DTN Messenger',
          debugShowCheckedModeBanner: false,
          theme: AppTheme.light,
          darkTheme: AppTheme.dark,
          themeMode: settings.themeMode,
          home: const ConversationsScreen(),
        );
      },
    );
  }
}
