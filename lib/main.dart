import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '花友居',
      theme: ThemeData(
        primarySwatch: Colors.green,
      ),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  Future<void> _launchUrl(String path) async {
    final Uri url = Uri.parse('https://mgm3000.pythonanywhere.com$path');
    if (!await launchUrl(url)) {
      throw Exception('Could not launch $url');
    }
  }

  @override
  Widget build(BuildContext context) {
    final sections = [
      {'name': '铁线莲', 'description': '', 'path': '/tiexianhua'},
      {
        'name': '苦苣苔科花卉图鉴区',
        'description': '苦苣苔科植物采名与品种辨识相关，及具有品种名称的植株开花照图文。',
        'path': '/kujutai'
      },
      {'name': '球根植物', 'description': '幻彩缤纷、终年藏于地底的瑰丽宝石...', 'path': '/qiugen'},
      {
        'name': '木本植物',
        'description': '它们像花园里的静待破晓，外表未必约丽华彩，却坚强地站定，成为恒久的守望。',
        'path': '/muben'
      },
      {'name': '兰科植物', 'description': '兰花栽培鉴赏和经验交流', 'path': '/lanke'},
      {
        'name': '野生植物',
        'description': '高高原上草，一岁一枯荣。野火烧不尽，春风吹又生。',
        'path': '/yesheng'
      },
      {
        'name': '果菜园',
        'description': '有没有时间？来来来，我们一起采用心品尝生活的滋味。。。',
        'path': '/guocai'
      },
      {
        'name': '药用与香草植物',
        'description': '走近药用植物，感受生活，缓解身心，自己动手DIY体验生活',
        'path': '/yaocao'
      },
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Text('花友居'),
        actions: [
          TextButton(
            onPressed: () => _launchUrl('/login'),
            child: const Text('登录', style: TextStyle(color: Colors.white)),
          ),
          TextButton(
            onPressed: () => _launchUrl('/register'),
            child: const Text('注册', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
      body: ListView.builder(
        itemCount: sections.length,
        itemBuilder: (context, index) {
          final section = sections[index];
          return Card(
            margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            child: ListTile(
              title: Text(section['name']!),
              subtitle: Text(
                section['description']!,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              onTap: () => _launchUrl(section['path']!),
            ),
          );
        },
      ),
    );
  }
}
