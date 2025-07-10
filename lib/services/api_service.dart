import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiService {
  static const String baseUrl = 'https://mgm3000.pythonanywhere.com';
  static const String apiUrl = '$baseUrl/api';

  // 登录方法
  Future<Map<String, dynamic>> login(String username, String password) async {
    try {
      final response = await http.post(
        Uri.parse('$apiUrl/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'username': username,
          'password': password,
        }),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
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
        Uri.parse('$apiUrl/register'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'username': username,
          'password': password,
        }),
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
      final response = await http.get(Uri.parse('$apiUrl/forums'));
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      }
      return [];
    } catch (e) {
      return [];
    }
  }

  // 获取论坛主题列表
  Future<List<dynamic>> getForumTopics(int forumId) async {
    try {
      final response =
          await http.get(Uri.parse('$apiUrl/forum/$forumId/topics'));
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      }
      return [];
    } catch (e) {
      return [];
    }
  }

  // 创建新主题
  Future<Map<String, dynamic>> createTopic(
      int forumId, String title, String content) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username') ?? '';

      final response = await http.post(
        Uri.parse('$apiUrl/topic/new'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'forum_id': forumId.toString(),
          'title': title,
          'content': content,
          'username': username,
        }),
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
        Uri.parse('$apiUrl/reply/$topicId'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'content': content,
          'username': username,
        }),
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
