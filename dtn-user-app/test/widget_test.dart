// DTN Messenger — Widget Smoke Test

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:dtn_messenger/app/app_theme.dart';

void main() {
  testWidgets('AppTheme smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        darkTheme: AppTheme.dark,
        home: const Scaffold(
          body: Center(child: Text('DTN Messenger Smoke Test')),
        ),
      ),
    );

    expect(find.text('DTN Messenger Smoke Test'), findsOneWidget);
  });
}
