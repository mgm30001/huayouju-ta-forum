import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';

class AuthProvider with ChangeNotifier {
  bool _isLoggedIn = false;
  String _username = '';
  final ApiService _apiService = ApiService();

  bool get isLoggedIn => _isLoggedIn;
  String get username => _username;

  AuthProvider() {
    _checkLoginStatus();
  }

  Future<void> _checkLoginStatus() async {
    final prefs = await SharedPreferences.getInstance();
    _isLoggedIn = prefs.getBool('isLoggedIn') ?? false;
    _username = prefs.getString('username') ?? '';
    notifyListeners();
  }

  Future<Map<String, dynamic>> login(String username, String password) async {
    final result = await _apiService.login(username, password);
    if (result['success']) {
      _isLoggedIn = true;
      _username = username;
      notifyListeners();
    }
    return result;
  }

  Future<Map<String, dynamic>> register(
      String username, String password) async {
    return await _apiService.register(username, password);
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.clear();
    _isLoggedIn = false;
    _username = '';
    notifyListeners();
  }
}
