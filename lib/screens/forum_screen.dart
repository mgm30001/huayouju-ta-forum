import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/api_service.dart';
import 'topic_screen.dart';

class ForumScreen extends StatefulWidget {
  final int forumId;
  final String forumName;

  const ForumScreen({
    super.key,
    required this.forumId,
    required this.forumName,
  });

  @override
  State<ForumScreen> createState() => _ForumScreenState();
}

class _ForumScreenState extends State<ForumScreen> {
  late Future<Map<String, dynamic>> _topicsFuture;

  @override
  void initState() {
    super.initState();
    _loadTopics();
  }

  void _loadTopics() {
    final apiService = context.read<ApiService>();
    _topicsFuture = apiService.getForumTopics(widget.forumId);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.forumName),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          setState(() {
            _loadTopics();
          });
        },
        child: FutureBuilder<Map<String, dynamic>>(
          future: _topicsFuture,
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
                          _loadTopics();
                        });
                      },
                      child: const Text('重试'),
                    ),
                  ],
                ),
              );
            }

            final topics = snapshot.data!['topics'] as List<dynamic>;
            return ListView.builder(
              itemCount: topics.length,
              itemBuilder: (context, index) {
                final topic = topics[index];
                return Card(
                  margin: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  child: ListTile(
                    title: Text(topic['title']),
                    subtitle: Text(
                      '作者: ${topic['author']} • ${topic['created_at']}',
                    ),
                    trailing: Text('回复: ${topic['reply_count']}'),
                    onTap: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (context) => TopicScreen(
                            topicId: topic['id'],
                            topicTitle: topic['title'],
                          ),
                        ),
                      );
                    },
                  ),
                );
              },
            );
          },
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          // TODO: 实现发帖功能
        },
        child: const Icon(Icons.add),
      ),
    );
  }
}
