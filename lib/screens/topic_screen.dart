import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_html/flutter_html.dart';
import '../services/api_service.dart';

class TopicScreen extends StatefulWidget {
  final int topicId;
  final String topicTitle;

  const TopicScreen({
    super.key,
    required this.topicId,
    required this.topicTitle,
  });

  @override
  State<TopicScreen> createState() => _TopicScreenState();
}

class _TopicScreenState extends State<TopicScreen> {
  late Future<Map<String, dynamic>> _topicFuture;
  final _replyController = TextEditingController();
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    _loadTopic();
  }

  @override
  void dispose() {
    _replyController.dispose();
    super.dispose();
  }

  void _loadTopic() {
    final apiService = context.read<ApiService>();
    _topicFuture = apiService.getTopic(widget.topicId);
  }

  Future<void> _submitReply() async {
    if (_replyController.text.trim().isEmpty) return;

    setState(() => _isSubmitting = true);

    try {
      final apiService = context.read<ApiService>();
      await apiService.createReply(
        widget.topicId,
        _replyController.text,
      );
      _replyController.clear();
      setState(() {
        _loadTopic();
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('发表回复失败: ${e.toString()}')),
      );
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.topicTitle),
      ),
      body: Column(
        children: [
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                setState(() {
                  _loadTopic();
                });
              },
              child: FutureBuilder<Map<String, dynamic>>(
                future: _topicFuture,
                builder: (context, snapshot) {
                  if (snapshot.connectionState == ConnectionState.waiting) {
                    return const Center(child: CircularProgressIndicator());
                  }

                  if (snapshot.hasError) {
                    return Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text('加载失败: ${snapshot.error}'),
                          const SizedBox(height: 16),
                          ElevatedButton(
                            onPressed: () {
                              setState(() {
                                _loadTopic();
                              });
                            },
                            child: const Text('重试'),
                          ),
                        ],
                      ),
                    );
                  }

                  final topic = snapshot.data!;
                  final replies = topic['replies'] as List<dynamic>;

                  return ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      Card(
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                topic['title'],
                                style: Theme.of(context).textTheme.titleLarge,
                              ),
                              const SizedBox(height: 8),
                              Text(
                                '作者: ${topic['author']} • ${topic['created_at']}',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                              const Divider(),
                              Html(data: topic['content']),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      Text(
                        '回复 (${replies.length})',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 8),
                      ...replies.map((reply) => Card(
                            margin: const EdgeInsets.only(bottom: 8),
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Text(
                                        reply['author'],
                                        style: const TextStyle(
                                          fontWeight: FontWeight.bold,
                                        ),
                                      ),
                                      const SizedBox(width: 8),
                                      Text(
                                        reply['created_at'],
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodySmall,
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 8),
                                  Html(data: reply['content']),
                                ],
                              ),
                            ),
                          )),
                    ],
                  );
                },
              ),
            ),
          ),
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: Theme.of(context).cardColor,
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.1),
                  blurRadius: 4,
                  offset: const Offset(0, -2),
                ),
              ],
            ),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _replyController,
                    decoration: const InputDecoration(
                      hintText: '发表回复...',
                      border: OutlineInputBorder(),
                    ),
                    maxLines: null,
                  ),
                ),
                const SizedBox(width: 8),
                IconButton(
                  onPressed: _isSubmitting ? null : _submitReply,
                  icon: _isSubmitting
                      ? const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.send),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
