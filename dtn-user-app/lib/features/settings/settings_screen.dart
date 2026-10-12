// DTN Messenger — Settings & Diagnostics Screen

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'settings_provider.dart';
import '../../core/transport/dtn_client.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController _nameCtrl;
  late TextEditingController _endpointCtrl;
  Map<String, dynamic>? _diags;
  Map<String, dynamic>? _storage;

  @override
  void initState() {
    super.initState();
    final prov = context.read<SettingsProvider>();
    _nameCtrl = TextEditingController(text: prov.config.displayName);
    _endpointCtrl = TextEditingController(text: prov.config.endpointUrl ?? '');
    _loadDiags();
  }

  Future<void> _loadDiags() async {
    final client = context.read<DtnClient>();
    final storage = await context.read<SettingsProvider>().getStorageStats();
    final diags = await client.getDiagnostics();
    if (mounted) {
      setState(() {
        _storage = storage;
        _diags = diags;
      });
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _endpointCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings & Diagnostics')),
      body: Consumer<SettingsProvider>(
        builder: (_, prov, __) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // ── Identity ──────────────────────────────────────────────────

              _SectionHeader('Identity'),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _InfoRow('Node ID', prov.config.nodeId),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _nameCtrl,
                        decoration: const InputDecoration(
                          labelText: 'Display Name',
                        ),
                        onSubmitted: (v) => prov.setDisplayName(v),
                      ),
                      const SizedBox(height: 8),
                      Align(
                        alignment: Alignment.centerRight,
                        child: ElevatedButton(
                          onPressed: () => prov.setDisplayName(_nameCtrl.text),
                          child: const Text('Save Name'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 16),

              // ── Connectivity ──────────────────────────────────────────────
              _SectionHeader('Connectivity'),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: prov.config.isSimulated
                                  ? Colors.orange.shade100
                                  : Colors.green.shade100,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              prov.config.isSimulated
                                  ? '⚠ SIMULATION MODE'
                                  : '✓ REAL ENDPOINT',
                              style: TextStyle(
                                fontWeight: FontWeight.w700,
                                fontSize: 12,
                                color: prov.config.isSimulated
                                    ? Colors.deepOrange
                                    : Colors.green.shade800,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Force simulation mode'),
                        subtitle: const Text(
                          'Override endpoint and use synthetic peers',
                        ),
                        value: prov.config.simulationMode,
                        onChanged: (v) => prov.setSimulationMode(v),
                      ),
                      const Divider(height: 16),
                      TextField(
                        controller: _endpointCtrl,
                        decoration: const InputDecoration(
                          labelText: 'DTN Gateway URL',
                          hintText: 'http://192.168.1.10:8765',
                        ),
                      ),
                      const SizedBox(height: 8),
                      Align(
                        alignment: Alignment.centerRight,
                        child: ElevatedButton(
                          onPressed: () {
                            final url = _endpointCtrl.text.trim();
                            prov.setEndpointUrl(url.isEmpty ? null : url);
                          },
                          child: const Text('Save Endpoint'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 16),

              // ── Theme ─────────────────────────────────────────────────────
              _SectionHeader('Appearance'),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Theme',
                        style: TextStyle(fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 8),
                      SegmentedButton<String>(
                        selected: {prov.config.themeMode},
                        onSelectionChanged: (s) => prov.setThemeMode(s.first),
                        segments: const [
                          ButtonSegment(value: 'system', label: Text('System')),
                          ButtonSegment(value: 'light', label: Text('Light')),
                          ButtonSegment(value: 'dark', label: Text('Dark')),
                        ],
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 16),

              // ── Limits ────────────────────────────────────────────────────
              _SectionHeader('Limits'),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: _InfoRow(
                    'Max attachment size',
                    '${prov.config.maxAttachmentMb} MB',
                  ),
                ),
              ),

              const SizedBox(height: 16),

              // ── Storage ───────────────────────────────────────────────────
              _SectionHeader('Storage'),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: _storage == null
                      ? const Center(child: CircularProgressIndicator())
                      : Column(
                          children: [
                            _InfoRow(
                              'Conversations',
                              '${_storage!['conversations'] ?? 0}',
                            ),
                            _InfoRow(
                              'Messages',
                              '${_storage!['messages'] ?? 0}',
                            ),
                          ],
                        ),
                ),
              ),

              const SizedBox(height: 16),

              // ── Diagnostics ───────────────────────────────────────────────
              _SectionHeader('Diagnostics'),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: _diags == null
                      ? Column(
                          children: [
                            const CircularProgressIndicator(),
                            const SizedBox(height: 8),
                            ElevatedButton(
                              onPressed: _loadDiags,
                              child: const Text('Refresh'),
                            ),
                          ],
                        )
                      : Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            ..._diags!.entries.map(
                              (e) => _InfoRow(
                                e.key,
                                e.value?.toString() ?? 'null',
                              ),
                            ),
                            const SizedBox(height: 8),
                            ElevatedButton.icon(
                              onPressed: _loadDiags,
                              icon: const Icon(Icons.refresh),
                              label: const Text('Refresh'),
                            ),
                          ],
                        ),
                ),
              ),

              const SizedBox(height: 32),
            ],
          );
        },
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader(this.title);

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 8, left: 4),
    child: Text(
      title.toUpperCase(),
      style: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w700,
        letterSpacing: 0.8,
        color: Theme.of(context).colorScheme.outline,
      ),
    ),
  );
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;
  const _InfoRow(this.label, this.value);

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 140,
          child: Text(
            label,
            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
          ),
        ),
        Expanded(
          child: SelectableText(value, style: const TextStyle(fontSize: 13)),
        ),
      ],
    ),
  );
}
