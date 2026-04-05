# 🔐 企业微信应用消息配置指南

这是最安全的微信通知方式，消息直接从您的服务器发送到企业微信，不经过任何第三方服务器。

## 前提条件

- 有企业微信账号（个人可免费注册企业）
- 能访问企业微信管理后台

## 配置步骤

### 第1步：获取企业ID (CorpID)

1. 登录企业微信管理后台: https://work.weixin.qq.com/
2. 点击左侧菜单 **"我的企业"**
3. 在 **"企业信息"** 页面底部找到 **"企业ID"**
4. 复制这个ID（如：`ww1234567890abcdef`）

### 第2步：创建应用并获取 AgentID 和 Secret

1. 在管理后台，点击左侧菜单 **"应用管理"**
2. 点击 **"创建应用"**
3. 填写应用信息：
   - **应用名称**: 股票助手（或任意名称）
   - **应用logo**: 上传一个图标（可选）
   - **可见范围**: 选择你自己（或需要接收消息的人）
4. 点击 **"创建应用"**
5. 创建成功后，在应用详情页找到：
   - **AgentId**: 如 `1000002`
   - **Secret**: 点击查看，复制（如 `abcdefg...`）

### 第3步：配置 notifier.json

编辑 `data/stock-data/notifier.json`：

```json
{
  "wecom_app": {
    "corpid": "ww1234567890abcdef",
    "agentid": "1000002",
    "secret": "YOUR_APP_SECRET_HERE",
    "touser": "@all"
  }
}
```

**参数说明：**
- `corpid`: 企业ID
- `agentid`: 应用ID
- `secret`: 应用Secret
- `touser`: 消息接收者
  - `@all` = 发送给应用可见范围内的所有人
  - `UserID1` = 发送给指定用户
  - `UserID1|UserID2` = 发送给多个用户

### 第4步：测试

```bash
docker exec openclaw python3 /home/node/.openclaw/skills/china-stock/notifier.py --test --channel wecom_app
```

如果成功，你的企业微信会收到测试消息！

## 常见问题

### Q: 我没有企业微信，可以免费注册吗？
A: 可以！访问 https://work.weixin.qq.com/wework_admin/register_wx 免费注册。个人也可以注册"企业"，不需要真实企业资质。

### Q: Secret 在哪里查看？
A: 在应用详情页，找到"Secret"一行，点击"查看"按钮，需要管理员扫码确认后才能看到。

### Q: 消息发送失败怎么办？
A: 检查：
1. CorpID、AgentID、Secret 是否正确复制（无多余空格）
2. 应用的可见范围是否包含你自己
3. 网络是否能访问 `qyapi.weixin.qq.com`

### Q: 如何只发给自己不发给其他人？
A: 
1. 在应用管理中，将可见范围设置为只包含你自己
2. 或者在 `touser` 中填写你的企业微信 UserID

## 安全性

| 方面 | 说明 |
|------|------|
| 数据传输 | 直接从你的服务器 → 腾讯服务器，不经过第三方 |
| API认证 | 使用 OAuth 2.0，access_token 有效期2小时 |
| Secret | 只有管理员扫码确认才能查看 |
| 消息加密 | HTTPS加密传输 |

这是腾讯官方提供的企业级通信解决方案，安全性有保障！

## 备选方案

如果不想注册企业微信，可以使用：
- **企业微信群机器人** (`wecom`): 需要企业微信但配置更简单
- **Server酱** (`serverchan`): 第三方服务，但简单易用
