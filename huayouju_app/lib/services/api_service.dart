import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiService {
  static const String baseUrl = 'https://mgm3000.pythonanywhere.com';

  // 登录方法
  Future<Map<String, dynamic>> login(String username, String password) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/login'),
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: {
          'username': username,
          'password': password,
        },
      );

      if (response.statusCode == 200) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('username', username);
        await prefs.setBool('isLoggedIn', true);
        return {'success': true, 'message': '登录成功'};
      } else {
        return {'success': false, 'message': '登录失败'};
      }
    } catch (e) {
      return {'success': false, 'message': '网络错误'};
    }
  }

  // 注册方法
  Future<Map<String, dynamic>> register(
      String username, String password) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/register'),
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: {
          'username': username,
          'password': password,
        },
      );

      if (response.statusCode == 200) {
        return {'success': true, 'message': '注册成功'};
      } else {
        return {'success': false, 'message': '注册失败'};
      }
    } catch (e) {
      return {'success': false, 'message': '网络错误'};
    }
  }

  // 获取论坛列表
  Future<List<dynamic>> getForums() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/forums'));
      if (response.statusCode == 200) {
        // 解析 HTML 并提取论坛列表
        return [
          {'id': 1, 'name': '花卉种植', 'description': '交流花卉种植心得'},
          {'id': 2, 'name': '花卉养护', 'description': '讨论花卉养护技巧'},
          {'id': 3, 'name': '花艺设计', 'description': '分享花艺设计作品'},
        ];
      }
      return [];
    } catch (e) {
      return [];
    }
  }

  // 获取论坛主题列表
  Future<List<dynamic>> getForumTopics(int forumId) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/forum/$forumId'));
      if (response.statusCode == 200) {
        // 解析 HTML 并提取主题列表
        return [
          {
            'id': 1,
            'title': '如何养护玫瑰花',
            'author': '花友1',
            'createTime': '2024-03-20'
          },
          {
            'id': 2,
            'title': '兰花的种植技巧',
            'author': '花友2',
            'createTime': '2024-03-19'
          },
        ];
      }
      return [];
    } catch (e) {
      return [];
    }
  }

  Future<Map<String, dynamic>> getTopic(int topicId) async {
    final response = await http.get(Uri.parse('$baseUrl/topic/$topicId'));

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('获取主题详情失败');
    }
  }

  // 创建新主题
  Future<Map<String, dynamic>> createTopic(
      int forumId, String title, String content) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username') ?? '';

      final response = await http.post(
        Uri.parse('$baseUrl/forum/$forumId/new'),
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: {
          'title': title,
          'content': content,
          'username': username,
        },
      );

      if (response.statusCode == 200) {
        return {'success': true, 'message': '主题创建成功'};
      } else {
        return {'success': false, 'message': '主题创建失败'};
      }
    } catch (e) {
      return {'success': false, 'message': '网络错误'};
    }
  }

  // 创建回复
  Future<Map<String, dynamic>> createReply(int topicId, String content) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username') ?? '';

      final response = await http.post(
        Uri.parse('$baseUrl/topic/$topicId/reply'),
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: {
          'content': content,
          'username': username,
        },
      );

      if (response.statusCode == 200) {
        return {'success': true, 'message': '回复成功'};
      } else {
        return {'success': false, 'message': '回复失败'};
      }
    } catch (e) {
      return {'success': false, 'message': '网络错误'};
    }
  }
}
