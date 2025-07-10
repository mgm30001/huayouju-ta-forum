import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/api_service.dart';
import '../providers/auth_provider.dart';
import 'package:flutter_html/flutter_html.dart';

class TopicScreen extends StatefulWidget {
  final int topicId;

  const TopicScreen({
    super.key,
    required this.topicId,
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
    final apiService = Provider.of<ApiService>(context, listen: false);
    _topicFuture = apiService.getTopic(widget.topicId);
  }

  Future<void> _submitReply() async {
    if (_replyController.text.isEmpty) return;

    setState(() => _isSubmitting = true);

    try {
      final apiService = Provider.of<ApiService>(context, listen: false);
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
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isLoggedIn = context.watch<AuthProvider>().isLoggedIn;

    return Scaffold(
      appBar: AppBar(
        title: const Text('主题详情'),
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

                  final topic = snapshot.data!['topic'];
                  final replies = snapshot.data!['replies'] as List;

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
                                '${topic['author_name']} • ${topic['created_at']}',
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
                                    reply['author_name'],
                                    style: Theme.of(context).textTheme.titleSmall,
                                  ),
                                  const Spacer(),
                                  Text(
                                    reply['created_at'],
                                    style: Theme.of(context).textTheme.bodySmall,
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
          if (isLoggedIn)
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
                      textInputAction: TextInputAction.newline,
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