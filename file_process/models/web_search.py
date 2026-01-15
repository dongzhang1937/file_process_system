"""
网络搜索服务模块
支持Google、百度、Bing及自定义搜索引擎
"""
import requests
import json
from urllib.parse import urlencode, quote_plus
from config.logging_config import logger
from .llm_config import WebSearchConfigManager


class WebSearchService:
    """网络搜索服务"""
    
    def __init__(self, config=None):
        """
        初始化搜索服务
        
        Args:
            config: 搜索配置，如果为None则使用默认配置
        """
        self.config = config or WebSearchConfigManager.get_default_config()
        if not self.config:
            logger.warning("未找到网络搜索配置")
    
    def search(self, query, num_results=5, custom_urls=None):
        """
        执行搜索
        
        Args:
            query: 搜索关键词
            num_results: 返回结果数量
            custom_urls: 指定搜索的网站列表（可选）
        
        Returns:
            搜索结果列表 [{'title': '', 'url': '', 'snippet': ''}, ...]
        """
        if not self.config:
            return []
        
        search_engine = self.config.get('search_engine', 'google')
        
        # 如果指定了自定义网址，添加site限制
        if custom_urls:
            site_query = ' OR '.join([f'site:{url}' for url in custom_urls])
            query = f"({query}) ({site_query})"
        
        try:
            if search_engine == 'google':
                return self._search_google(query, num_results)
            elif search_engine == 'baidu':
                return self._search_baidu(query, num_results)
            elif search_engine == 'bing':
                return self._search_bing(query, num_results)
            elif search_engine == 'custom':
                return self._search_custom(query, num_results)
            else:
                logger.error(f"不支持的搜索引擎: {search_engine}")
                return []
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []
    
    def _search_google(self, query, num_results):
        """Google自定义搜索"""
        api_key = self.config.get('api_key')
        api_url = self.config.get('api_url')
        extra_params = self.config.get('extra_params', {}) or {}
        
        # Google需要cx参数（自定义搜索引擎ID）
        cx = extra_params.get('cx', '')
        
        params = {
            'key': api_key,
            'cx': cx,
            'q': query,
            'num': min(num_results, 10)  # Google最多返回10条
        }
        
        response = requests.get(api_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('items', []):
            results.append({
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', '')
            })
        
        return results
    
    def _search_baidu(self, query, num_results):
        """百度搜索（使用百度开放平台API）"""
        api_key = self.config.get('api_key')
        api_url = self.config.get('api_url')
        
        # 百度搜索API实现
        # 注意：实际使用需要根据百度API文档调整
        headers = {
            'Content-Type': 'application/json'
        }
        
        params = {
            'apikey': api_key,
            'query': query,
            'num': num_results
        }
        
        response = requests.get(api_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('results', []):
            results.append({
                'title': item.get('title', ''),
                'url': item.get('url', ''),
                'snippet': item.get('abstract', '')
            })
        
        return results
    
    def _search_bing(self, query, num_results):
        """Bing搜索"""
        api_key = self.config.get('api_key')
        api_url = self.config.get('api_url')
        
        headers = {
            'Ocp-Apim-Subscription-Key': api_key
        }
        
        params = {
            'q': query,
            'count': num_results,
            'mkt': 'zh-CN'
        }
        
        response = requests.get(api_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('webPages', {}).get('value', []):
            results.append({
                'title': item.get('name', ''),
                'url': item.get('url', ''),
                'snippet': item.get('snippet', '')
            })
        
        return results
    
    def _search_custom(self, query, num_results):
        """自定义搜索引擎"""
        api_key = self.config.get('api_key')
        api_url = self.config.get('api_url')
        extra_params = self.config.get('extra_params', {}) or {}
        
        # 构建请求
        method = extra_params.get('method', 'GET').upper()
        headers = extra_params.get('headers', {})
        
        # 添加API密钥到请求头或参数
        key_location = extra_params.get('key_location', 'header')
        key_name = extra_params.get('key_name', 'Authorization')
        
        if key_location == 'header':
            headers[key_name] = api_key
        
        params = {
            'query': query,
            'num': num_results
        }
        
        # 合并额外参数
        if extra_params.get('query_params'):
            params.update(extra_params['query_params'])
        
        if method == 'GET':
            response = requests.get(api_url, params=params, headers=headers, timeout=30)
        else:
            response = requests.post(api_url, json=params, headers=headers, timeout=30)
        
        response.raise_for_status()
        data = response.json()
        
        # 解析结果（根据配置的字段映射）
        results_path = extra_params.get('results_path', 'results')
        title_field = extra_params.get('title_field', 'title')
        url_field = extra_params.get('url_field', 'url')
        snippet_field = extra_params.get('snippet_field', 'snippet')
        
        items = data
        for key in results_path.split('.'):
            items = items.get(key, [])
        
        results = []
        for item in items:
            results.append({
                'title': item.get(title_field, ''),
                'url': item.get(url_field, ''),
                'snippet': item.get(snippet_field, '')
            })
        
        return results


class DirectUrlFetcher:
    """直接URL内容抓取器"""
    
    @staticmethod
    def fetch_content(url, timeout=30):
        """
        抓取指定URL的内容
        
        Args:
            url: 目标URL
            timeout: 超时时间
        
        Returns:
            {'title': '', 'content': '', 'url': ''}
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            # 简单提取内容（实际使用可以用BeautifulSoup等）
            from html.parser import HTMLParser
            
            class ContentExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.title = ''
                    self.content = []
                    self.in_title = False
                    self.in_script = False
                    self.in_style = False
                
                def handle_starttag(self, tag, attrs):
                    if tag == 'title':
                        self.in_title = True
                    elif tag == 'script':
                        self.in_script = True
                    elif tag == 'style':
                        self.in_style = True
                
                def handle_endtag(self, tag):
                    if tag == 'title':
                        self.in_title = False
                    elif tag == 'script':
                        self.in_script = False
                    elif tag == 'style':
                        self.in_style = False
                
                def handle_data(self, data):
                    if self.in_title:
                        self.title = data.strip()
                    elif not self.in_script and not self.in_style:
                        text = data.strip()
                        if text:
                            self.content.append(text)
            
            extractor = ContentExtractor()
            extractor.feed(response.text)
            
            return {
                'title': extractor.title,
                'content': ' '.join(extractor.content)[:5000],  # 限制内容长度
                'url': url
            }
        except Exception as e:
            logger.error(f"抓取URL内容失败 {url}: {e}")
            return None
