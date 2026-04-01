-- ============================================================
-- 更新 web_search_summary 场景的 Skills 默认模板
-- 新版：模板作为 user message 使用（非 system prompt），
-- 包含需求和搜索结果，由代码渲染后直接作为 user 消息发送
-- ============================================================

UPDATE `skills_configs` 
SET `system_prompt` = '请根据以下网络搜索结果，针对用户的技术需求生成准确、结构化的答案。

---

## 用户需求

{{requirement}}

---

## 搜索结果

{{search_results}}

---

## 回答要求

1. 综合多个搜索结果，给出全面、专业的回答
2. 重点关注该技术需求的**支持情况**、**实现方式**和**兼容性**
3. 如果不同来源有矛盾，请指出差异
4. 如果搜索结果不足以完整回答，请说明哪些方面信息不足
5. 回答要简洁、有条理，适合写入技术评估报告
6. 如有具体参考来源，标注出处',
    `variables_json` = '{"requirement": "用户需求", "search_results": "搜索结果内容"}',
    `updated_at` = NOW()
WHERE `scene_type` = 'web_search_summary' 
  AND `is_default` = 1 
  AND `is_active` = 1;
