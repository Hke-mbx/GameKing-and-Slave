# GameKing-and-Slave
欢迎来到《王与奴》！ 这是一款中世纪风格的1v1博弈对战型卡牌游戏。玩家操控国王方或奴隶方，使用策略，与对手进行心理战，争取游戏胜利。游戏时长仅在2~6分钟
王与奴 — 在线对战（MVP）
========================

包含：
- 后端：Node.js + Express + Socket.IO（server.js）
- 前端：静态文件 public/index.html（通过 Socket.IO 与后端通信）

本地运行（快速）：
1. 克隆或把代码放本地目录：
   npm install

2. 本地启动：
   npm run dev   # 需安装 nodemon
   或
   npm start

3. 打开浏览器访问：
   http://localhost:3000/   （若你把 index.html 放到 public/，后端会托管它）

部署建议：
- 把前端 static (public/index.html) 放到 GitHub Pages（仓库 Pages），并在页面上的“服务器地址”填写你后端的 WebSocket 地址（例如 wss://your-service.onrender.com）。
- 把后端 server.js 部署到 Render / Railway / Heroku 等（使用 Node 环境）。Render 的 Web Service 指向你的仓库并使用 `npm start`，配置 PORT 环境变量。

重要说明：
- 目前服务器使用内存存储（MVP）。重启服务器会丢失房间/用户数据。生产请用数据库与鉴权（JWT）。
- 同时请务必在服务器 match:start 时向每个玩家私发其手牌（`socket.to(userSocketId).emit('match:hand', hand)`），以便客户端能够显示真实卡面。
- 若需要我帮助你把前端和后端在 Render + GitHub Pages 上部署，并自动配置 `match:hand` 私有发放手牌，我可以替你生成修改后的 server.js 并写好部署步骤。

