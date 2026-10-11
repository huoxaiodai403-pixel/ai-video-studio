(() => {
  'use strict';
/* creative-methods:start */
const creativeMethods = [
  {
    "id": "huashu-art-motion",
    "title": "艺术与代码动画",
    "category": "animation",
    "route": "code-animation",
    "customStyle": "用具体对象、因果关系和一个主要动作解释机制。根据本次内容重新设计场景，稳定色板，避免标题卡代替动画。",
    "preparation": "一个要解释的机制；图表需准备真实数据、单位与来源。",
    "delivery": "网页生成可编辑的二维代码动画；复杂视觉语法可交给 Codex 深入制作。 可输入自己的主题与原稿，通过所选编剧和生成器重新制作；也可由 Codex 接管同一工程。示例复刻为独立选项。",
    "guidance": "先把内容拆成可见对象、动作与结论，再选择对应的动画语法；稳定媒介、色板和字体，逐镜改变构图。图表用真实数据、单位与来源，口播时间驱动 cue。当前适配器支持参数化柱状图与折线图。",
    "sampleTitle": "先找到瓶颈 · 机制动画",
    "source": "https://github.com/alchaincyf/huashu-art-motion",
    "example": {
      "title": "先找到瓶颈 · 机制动画",
      "brief": "原创教学示意，非真实系统性能测试。使用花叔先对象、动作、机制再结论的方法，演示输入更快而处理不变时队列积压；不泛化为所有系统的性能结论。",
      "style": "黑蓝底、珊瑚与青绿，具体任务方块流经处理节点；以队列累积、局部放大和前后比较解释机制。",
      "character": ""
    },
    "shots": [
      {
        "narration": "假设任务不断送来，每次只能处理一个。",
        "visual": "方块从输入端进入单个处理节点",
        "action": "任务匀速进入，处理节点逐个亮起",
        "camera": "完整流程图"
      },
      {
        "narration": "送得更快，处理速度却没变，等待的任务就排起了队。",
        "visual": "处理节点前任务从两个累积为六个",
        "action": "输入增多，队列加长，出口保持原节奏",
        "camera": "输入与队列中景"
      },
      {
        "narration": "这时先找出卡住的环节，比继续催着提交更有用。",
        "visual": "放大处理节点，队列和节点用强调色分开",
        "action": "光圈聚焦受限节点，输入端维持中性色",
        "camera": "瓶颈节点特写"
      },
      {
        "narration": "让输入和处理相互匹配，再观察队列有没有缩短。",
        "visual": "上下两条示意流程对照，下面的队列逐渐缩短",
        "action": "下方任务按处理节奏流动，最终剩一格等待",
        "camera": "前后对照全景"
      }
    ]
  },
  {
    "id": "vox-director",
    "title": "纸张拼贴讲解",
    "category": "knowledge",
    "route": "character-story",
    "customStyle": "纸张拼贴讲解。为本次内容生成完整拼贴静帧；纸张边缘、材质与明确前后景，主体动作和相机运动分别设计。",
    "preparation": "讲解文稿、可使用的图片与素材来源。",
    "delivery": "网页先生成配图与旁白；精细纸张分层和拼贴运动由 Codex 配合制作。 可输入自己的主题与原稿，通过所选编剧和生成器重新制作；也可由 Codex 接管同一工程。示例复刻为独立选项。",
    "guidance": "先按主题选择叙事结构，再制作每个节拍的完整拼贴构图；画面质感与运动分开设计。需要时为同一节拍安排全景和细节镜头；相机运动和纸片动作分别描述，高潮留停顿。",
    "sampleTitle": "慢一点，看见这座城 · 拼贴短片",
    "source": "https://github.com/Alisa0808/vox-director",
    "example": {
      "title": "慢一点，看见这座城 · 拼贴短片",
      "brief": "原创城市骑行小故事。使用自有或新生成的透明单车图层，不能把拼贴位移称为模型生成的人物运动。",
      "style": "奶油纸底、朱红单车剪贴、森林绿与钴蓝纸片；主物体、地图与文字分别运动。",
      "character": ""
    },
    "shots": [
      {
        "narration": "赶路的时候，城市只剩下一个终点。",
        "visual": "地图连线与终点纸签，单车从左侧进入",
        "action": "地图纸片先落下，单车后滑入",
        "camera": "固定全景"
      },
      {
        "narration": "慢一点，才看见转角的树影和风。",
        "visual": "单车局部放大，蓝色风线与剪纸叶片",
        "action": "叶片轻摆，镜头缓慢推近车把",
        "camera": "局部近景"
      },
      {
        "narration": "选一条没走过的小路，让好奇心带路。",
        "visual": "路线分岔，金黄新路线逐段画出",
        "action": "路线与路标分别出现，单车沿图面平移",
        "camera": "俯看平面地图"
      },
      {
        "narration": "今天的收获，也可以是沿途。",
        "visual": "单车和三张彩色纸片组成最终海报",
        "action": "纸片独立入场，单车落位，定格收尾",
        "camera": "拉回完整构图"
      }
    ]
  },
  {
    "id": "hand-drawn-video-prompts",
    "title": "手绘蜡笔口播",
    "category": "knowledge",
    "route": "code-animation",
    "customStyle": "米白纸上的手绘蜡笔画。每个论点使用不同、具体的可视比喻；保持笔触一致，中文文字由后期制作。",
    "preparation": "一句核心观点，以及对应的可见比喻。",
    "delivery": "网页生成二维手绘动效与旁白；角色表演可换用角色叙事工作流。 可输入自己的主题与原稿，通过所选编剧和生成器重新制作；也可由 Codex 接管同一工程。示例复刻为独立选项。",
    "guidance": "按论点变化、因果、举例和结论拆镜，每镜一个可视隐喻。暖白纸、粗黑线和少量强调色构成稳定视觉语言；每镜提示写全主体、动作、空间与风格。精确中文、数字与字幕交给后期确定性文字层。",
    "sampleTitle": "先装重要的事 · 手绘讲解",
    "source": "https://github.com/kaomei/hand-drawn-video-prompts",
    "example": {
      "title": "先装重要的事 · 手绘讲解",
      "brief": "原创时间安排的视觉比喻，瓶子容量是示意，不是实验或精确统计。",
      "style": "暖白纸底、黑色粗线、黄蓝红蜡笔色；竖屏构图，逐笔画出与物体落下。",
      "character": ""
    },
    "shots": [
      {
        "narration": "零碎的小事，总能填满一天。",
        "visual": "沙粒不断落进玻璃罐",
        "action": "零散色点落下并在罐底堆积",
        "camera": "固定中景"
      },
      {
        "narration": "等到重要的事出现，却发现已经装不下。",
        "visual": "黄色大石头被已经填满的罐口挡住",
        "action": "石头下落，触碰沙堆后停住",
        "camera": "罐口近景"
      },
      {
        "narration": "换个顺序。先放进今天最重要的一件事。",
        "visual": "空罐里先放入一颗黄色大石头",
        "action": "画出罐子轮廓，大石头落到底部",
        "camera": "全景"
      },
      {
        "narration": "再让零碎的小事，去填剩下的空隙。",
        "visual": "蓝红沙粒落在石头两侧，石头保持可见",
        "action": "细粒绕过石头堆积，末态停留",
        "camera": "固定中景"
      }
    ]
  },
  {
    "id": "stickman-video-director",
    "title": "火柴人叙事",
    "category": "story",
    "route": "code-animation",
    "customStyle": "简洁火柴人动画。圆头细线身体，保持比例；每镜写清动作起点、接触、反馈和末态，以动作表达情绪。",
    "preparation": "短故事、角色比例，以及每一镜的主要动作。",
    "delivery": "网页制作二维动作叙事；需要模型生成的连续表演时使用角色叙事。 可输入自己的主题与原稿，通过所选编剧和生成器重新制作；也可由 Codex 接管同一工程。示例复刻为独立选项。",
    "guidance": "用开场矛盾、认知变化、具体机制、结论与收束组织叙事；按内容取舍，不编造秘密或冲突。锁定人物比例、线宽和声音，让角色通过具体动作改变场景，每镜写起始、动作和结束状态；横竖屏重新构图。",
    "sampleTitle": "先走一步 · 火柴人短片",
    "source": "https://github.com/kaomei/stickman-video-director",
    "example": {
      "title": "先走一步 · 火柴人短片",
      "brief": "原创寓言短片，验证连续配音、语义分镜、角色动作、字幕与成片。没有事实或效果承诺。",
      "style": "白底、黑色火柴人、金黄台阶。角色用双脚落点、重心和关节运动完成真正的迈步。",
      "character": ""
    },
    "shots": [
      {
        "narration": "总想一下登顶，脚反而迈不出去。",
        "visual": "左侧小人与右侧高墙形成尺度差",
        "action": "小人抬头，再抬脚试探高墙",
        "camera": "固定全景"
      },
      {
        "narration": "把眼前那一步，改成一个够得着的小台阶。",
        "visual": "高墙分解为四级金黄台阶",
        "action": "台阶依次降到可迈高度，小人转向第一阶",
        "camera": "固定中景"
      },
      {
        "narration": "先落下一只脚，再把重心移过去。",
        "visual": "放大脚部与身体重心",
        "action": "抬脚、落脚、移动身体、后脚跟上，动作有支撑点",
        "camera": "脚部特写"
      },
      {
        "narration": "今天先走一步，路就从这里开始。",
        "visual": "小人从第一级走到第二级，远方留白",
        "action": "连贯登阶后站稳，最后半秒保持完整末态",
        "camera": "回到全景"
      }
    ]
  },
  {
    "id": "kid-papercraft",
    "title": "纸艺祝福短片",
    "category": "story",
    "route": "code-animation",
    "customStyle": "温暖纸艺动画。折纸与剪纸材质，柔和阴影，角色比例一致；登场、个性祝福与温暖收尾，不能编造姓名年龄。",
    "preparation": "祝福内容；需要出现姓名和年龄时自行填写。",
    "delivery": "网页制作二维纸艺动效与配音；立体角色动画需另行制作。 可输入自己的主题与原稿，通过所选编剧和生成器重新制作；也可由 Codex 接管同一工程。示例复刻为独立选项。",
    "guidance": "围绕登场、个性化祝福、温暖收尾组织纸艺定格短片。沿用用户选定的角色、名字与年龄；纸张材质、柔和光线和比例保持一致。姓名与祝福文字用后期字幕，避免模型写错。",
    "sampleTitle": "给今天一点甜 · 纸艺祝福",
    "source": "https://github.com/kaomei/kid-papercraft",
    "example": {
      "title": "给今天一点甜 · 纸艺祝福",
      "brief": "原创小兔通用生日祝福。未提供孩子信息，样片不杜撰姓名和年龄。登场、祝福和生活叮嘱三段式，全部为可编辑二维纸艺动画。",
      "style": "奶油纸张、浅蓝与珊瑚色、真实折痕和一致右下投影。二维剪纸关节动画，12.5 fps 定格节奏。",
      "character": ""
    },
    "shots": [
      {
        "narration": "今天，把一张小小的纸，折成送给你的惊喜。",
        "visual": "折叠信封打开，原创纸兔从中探头",
        "action": "翻开信封盖，纸兔分两次探头并挥手",
        "camera": "竖屏全景"
      },
      {
        "narration": "生日快乐。愿你新的一岁，总有好奇心和笑声相伴。",
        "visual": "小兔推来纸艺蛋糕，星星随祝福落下",
        "action": "纸轮滚动带入蛋糕，星星以定格节奏飘落",
        "camera": "向蛋糕靠近的中景"
      },
      {
        "narration": "记得照顾好自己，好好吃饭，也好好睡觉。",
        "visual": "纸兔把碗、月亮和小床依次摆好",
        "action": "温柔的折纸翻面转场，月亮从碗后升起",
        "camera": "物件近景"
      },
      {
        "narration": "慢慢长大，勇敢出发。你的每一天，都值得被祝福。",
        "visual": "纸兔抱着一颗珊瑚色心，身后展开纸旗",
        "action": "心形展开后轻轻抬起，最终稳稳定格",
        "camera": "回到完整祝福构图"
      }
    ]
  },
  {
    "id": "classical-poem-silk-video",
    "title": "古诗词国风短片",
    "category": "knowledge",
    "route": "character-story",
    "customStyle": "国风绢本画卷，克制笔触与留白。先理解全诗，再逐句对应名物、空间层次和一个主动作。诗句在后期叠加。",
    "preparation": "核对过的诗词原文、作者，以及希望出现的意象。",
    "delivery": "网页生成国风配图、朗诵与字幕；精细局部雨水、涟漪合成可交给 Codex。 可输入自己的主题与原稿，通过所选编剧和生成器重新制作；也可由 Codex 接管同一工程。示例复刻为独立选项。",
    "guidance": "通读全诗后按诗句分组，记录每景的名物、一个主动作、近中远景及情绪职责。保留系列材质与时代感，让构图随诗意变化；运动来自现有的风、水、鸟与人物，不擅增主体。诗句以可编辑文字层叠加，保留环境声。",
    "sampleTitle": "春晓 · 逐句画卷",
    "source": "https://github.com/Mr-funny/hbg-classical-poem-silk-video",
    "example": {
      "title": "春晓 · 逐句画卷",
      "brief": "孟浩然《春晓》全文逐句分景。原文核对：https://zh.wikisource.org/wiki/春曉_(孟浩然)。本地版本为原创画卷加局部后期特效，非 Gemini I2V，不声称鸟体具有模型动作。",
      "style": "四景统一绢本国风，镜头固定；代码生成的雨丝、水波和字层与底图分开。",
      "character": ""
    },
    "shots": [
      {
        "narration": "春眠不觉晓。",
        "visual": "晨光照入窗棂与空榻，右侧逐句诗文",
        "action": "晨光微亮，细尘漂浮",
        "camera": "固定室内中景"
      },
      {
        "narration": "处处闻啼鸟。",
        "visual": "两只鸟栖在开花的枝头，花鸟特写",
        "action": "保持原鸟体，轻雾慢移；声音作为诗意解释",
        "camera": "固定花鸟近景"
      },
      {
        "narration": "夜来风雨声。",
        "visual": "回忆夜雨中的屋檐和石盆",
        "action": "局部雨丝与水波叠加，画面结构固定",
        "camera": "固定庭院全景"
      },
      {
        "narration": "花落知多少。",
        "visual": "石阶边的落花与水面倒影",
        "action": "轻缓同心水波，末尾停留完整诗句",
        "camera": "固定俯视细节"
      }
    ]
  },
  {
    "id": "hbg-life-simulation",
    "title": "人生故事漫画",
    "category": "story",
    "route": "character-story",
    "customStyle": "人物人生漫画，统一角色外貌服装与画风；根据情绪、地点和动作改变景别，保持事件连续。静图剪辑不可声称角色动画。",
    "preparation": "人物经历、角色关系与可核实资料，先选一个章节。",
    "delivery": "网页生成有声漫画短章；长篇需分章补齐素材并逐段检查。 可输入自己的主题与原稿，通过所选编剧和生成器重新制作；也可由 Codex 接管同一工程。示例复刻为独立选项。",
    "guidance": "保留原文、人物身份与关系，用真实连续配音作为主时间轴；在地点、行动、情绪或决定变化处换画面。结合远景、动作、双人、主观和物件细节，按实际音轨审查素材覆盖，不能靠长时间缩放掩盖缺镜。",
    "sampleTitle": "修伞人 · 人生漫画",
    "source": "https://github.com/Mr-funny/hbg-life-simulation",
    "example": {
      "title": "修伞人 · 人生漫画",
      "brief": "原创虚构人生片段，保留连续旁白。开场快闪职业字卡后定格修伞人，再以四种景别组织人物、手部、开伞与离去。四格原图由内置 imagegen 生成，非视频模型动态。",
      "style": "黑色漫画格框，暖金与灰绿，固定黑发圆眼镜、绿围裙的虚构修伞人。图片推拉平移明确作为剪辑运动。",
      "character": ""
    },
    "shots": [
      {
        "narration": "今天体验的人生副本是，",
        "visual": "不同职业字卡短促切换",
        "action": "送信人、木匠、修伞人字卡快闪后停止",
        "camera": "平面标题"
      },
      {
        "narration": "修伞人。",
        "visual": "门口主角定格，职业标题显现",
        "action": "固定主角初次亮相",
        "camera": "定格全景"
      },
      {
        "narration": "你推开小店的门，第一把伞已经在等你。",
        "visual": "同一修伞人在晨雨中推开旧店门",
        "action": "静图轻推近，保持人物与店铺",
        "camera": "室内广角建立空间"
      },
      {
        "narration": "旧伞骨卡住了，你先停下来，找准那一处弯折。",
        "visual": "双手用钳子修整一处伞骨",
        "action": "静图由左向右，停在工具与折点",
        "camera": "手部极近特写"
      },
      {
        "narration": "撑开的那一刻，雨声又落回了伞面。",
        "visual": "同一主角撑起修好的红伞",
        "action": "由近到远揭示完整伞面",
        "camera": "低机位中景"
      },
      {
        "narration": "你没有修好所有天气，只是让一个人能继续赶路。",
        "visual": "主角站在门边，看客人撑着同一红伞离开",
        "action": "静图横移，以街道留白收束",
        "camera": "门框中的远景"
      }
    ]
  },
  {
    "id": "simon-skills",
    "title": "白板与资料讲解",
    "category": "knowledge",
    "route": "whiteboard",
    "customStyle": "",
    "preparation": "一个问题、关键词和图形之间的关系。",
    "delivery": "在白板编辑器制作逐笔画面、旁白、字幕与封面；调查长片有独立入口。",
    "guidance": "以一条解释主线安排白板关键词、关系与图形，随旁白逐步呈现；资料长片另走章节、证据和素材覆盖流程。优先复用工作台已适配的 Simon 渲染与真实声音时间戳。",
    "sampleTitle": "一条消息，三步核对 · 有声白板",
    "source": "https://github.com/trustfuture/simon-skills",
    "example": {
      "title": "一条消息，三步核对 · 有声白板",
      "brief": "",
      "style": "",
      "character": ""
    },
    "shots": []
  },
  {
    "id": "director",
    "title": "人物故事与剧情导演",
    "category": "story",
    "route": "code-animation",
    "customStyle": "根据当前故事确定视角、因果与结尾。保持角色身份和动作连续性，分别设计主体行动和相机运动；不要每镜重新开始动作。",
    "preparation": "故事视角、角色约定、起因与结尾。",
    "delivery": "网页制作二维故事动画；写实表演可转角色叙事，复杂场景交给 Codex。 可输入自己的主题与原稿，通过所选编剧和生成器重新制作；也可由 Codex 接管同一工程。示例复刻为独立选项。",
    "guidance": "先判断个人经历、知识解释或人物冲突驱动，再选对应的视觉与声音设计。分开写人物参考的身份职责和每镜具体场景；每镜交代动作起点、可见反馈、结束状态与摄影机路径，相邻镜头不要重复已完成动作。",
    "sampleTitle": "手心里的小纸条 · 第一人称故事",
    "source": "https://github.com/s1dashu/director",
    "example": {
      "title": "手心里的小纸条 · 第一人称故事",
      "brief": "director 的 Storytime 模式，第一人称原创虚构，不冒充用户经历。事件从准备、卡壳、折纸、抬头到留存递进；角色动作由代码绘制，非 Seedance 人物表演。",
      "style": "原创二维人物故事，短发、青绿外套、杏色上衣和小纸条为固定身份锚点；靛蓝舞台与暖米色近景。",
      "character": ""
    },
    "shots": [
      {
        "narration": "第一次上台前，我把开场白写满了一张纸。",
        "visual": "后台等待的短发女生拿着写满字的纸",
        "action": "低头看稿，手中纸张轻轻抖动",
        "camera": "后台全景"
      },
      {
        "narration": "可灯一亮，我连第一句都找不到。",
        "visual": "舞台聚光灯下人物与展开的大纸张",
        "action": "灯亮，目光在密密的字行间移动",
        "camera": "人物中近景"
      },
      {
        "narration": "我停下来，把纸对折，只留下一句想说的话。",
        "visual": "双手在桌面上对折纸张，只露出一句话",
        "action": "纸面沿中线折叠，手指跟随折痕压下",
        "camera": "俯视手部特写"
      },
      {
        "narration": "抬头的时候，台下有人点了点头。",
        "visual": "从讲述者肩后看向台下几位听众",
        "action": "人物抬头，一名听众点头回应",
        "camera": "过肩反打"
      },
      {
        "narration": "那张小纸条，我到现在还留着。",
        "visual": "书桌抽屉中留下折好的同一张纸",
        "action": "手放下纸条后离开，画面安静停留",
        "camera": "纸条与抽屉近景"
      }
    ]
  },
  {
    "id": "book-sales-video",
    "title": "书评与图书推荐",
    "category": "knowledge",
    "route": "character-story",
    "customStyle": "围绕用户给出的书籍内容制作书评。整组规划书页、场景与阅读细节的景别；引用必须来自输入，不虚构书封、原文或购买事实。",
    "preparation": "书名、作者、核实过的原文与个人观点，注明引用来源。",
    "delivery": "网页制作有声书评短片；不自动抓取或核验书籍内容。 可输入自己的主题与原稿，通过所选编剧和生成器重新制作；也可由 Codex 接管同一工程。示例复刻为独立选项。",
    "guidance": "先核对书名、作者与原书事实，区分公开点评和书中观点，保留用户已确认口播。整段配音后按语义规划全组镜头，固定字幕安全区，变换景别和视角；精确书名、封面、字幕与音轨作为独立素材保存。",
    "sampleTitle": "一页一问 · 读论语",
    "source": "https://github.com/Kianzzz/book-sales-video",
    "example": {
      "title": "一页一问 · 读论语",
      "brief": "核对《论语·学而》公开原文：https://zh.wikisource.org/wiki/論語/學而第一 。开篇原句与现代阅读建议分开。封面为本项目原创书籍示意，不冒充出版社封面，不引用评分、销量或编造读者评论。",
      "style": "靛蓝线装书、米白纸和朱色书签；整组镜头从封面、原句、阅读桌面到远景变化，字幕固定在下方。",
      "character": ""
    },
    "shots": [
      {
        "narration": "读论语，可以先从一页里的一个问题开始。",
        "visual": "原创靛蓝线装书封面与小书签",
        "action": "封面从斜侧转正，书签轻落",
        "camera": "书籍三分之四视角"
      },
      {
        "narration": "开篇的学而时习之，把学习和反复实践放在一起。",
        "visual": "书页上显现学而时习之的原句",
        "action": "翻开纸页，原句逐组亮起",
        "camera": "俯视书页近景"
      },
      {
        "narration": "先选一句，再拿自己的经历来对照。哪里做到了，哪里还没做到。",
        "visual": "打开的书、便签与笔，便签写下自己的问题",
        "action": "笔尖移动留下一个问号，两张便签依次放入",
        "camera": "桌面斜侧中景"
      },
      {
        "narration": "别急着一次读完。把一个问题读明白，再往下走。",
        "visual": "书签留在这一页，画面拉远留下阅读空间",
        "action": "纸页轻合，书签保留，最后完整停留",
        "camera": "俯视远景"
      }
    ]
  }
];
/* creative-methods:end */
  const marker = method => `创作方法：${method.title} [${method.id}]`;
  window.StudioCreativeMethods = {
    list: creativeMethods,
    find: id => creativeMethods.find(method => method.id === id),
    fromPlan: plan => creativeMethods.find(method => method.id===plan?.method_id || (plan?.brief || '').includes(marker(method))),
    custom(method, blankPlan) { return {...blankPlan(),method_id:method.id,route:method.route,style:method.customStyle,character:'',shots:[]}; },
    seed(method, blankPlan, blankShot) {
      return {...blankPlan(), ...method.example, route: method.route,
        title: method.example.title + ' · 新创作',
        brief: [method.example.brief, marker(method), method.preparation, method.delivery].filter(Boolean).join('\n\n'),
        style: [method.example.style, method.guidance].filter(Boolean).join('\n'),
        shots: method.shots.map(shot => ({...blankShot(), ...shot}))};
    },
  };
  const host = document.getElementById('creative-methods');
  if (!host) return;
  document.getElementById('creative-methods-heading').textContent = `视频 Skill · ${creativeMethods.length} 种创作方法`;
  const element = (tag, text, className) => { const el = document.createElement(tag); if(text) el.textContent = text; if(className) el.className = className; return el; };
  for (const method of creativeMethods) {
    const card = element('article', '', 'workflow-card');
    card.dataset.flowCategory = method.category; card.id = method.id;
    card.dataset.search = [method.title, method.id, method.preparation, method.guidance].join(' ');
    card.append(element('span', '视频 Skill', 'hub-kicker'), element('h2', method.title), element('p', method.preparation, 'workflow-goal'));
    const details = element('details', '', 'workflow-details');
    details.append(element('summary', '准备与制作步骤'));
    const steps = element('ol');
    for (const text of ['核对题材、文稿和素材，确认本次制作范围。', method.route === 'whiteboard' ? '进入白板编辑器，编排旁白、关键词和逐笔布局。' : '载入可编辑示例，替换自己的内容并检查每一镜。', '选择配音，先生成样片；审看后生成整片，在作品库继续编辑。']) steps.append(element('li', text));
    details.append(steps, element('p', method.guidance, 'workflow-output'), element('p', method.delivery, 'workflow-note'));
    const source = element('a', '查看方法来源'); source.href = method.source; source.target = '_blank'; source.rel = 'noopener noreferrer'; details.append(source);
    const footer = element('div', '', 'hub-card-footer');
    const create = element('a', '使用此方法 →', 'workflow-link'); create.href = '/generation?' + new URLSearchParams({route:method.route, method:method.id});
    const samples = element('a', '查看已有作品', 'workflow-link'); samples.href = '/library?' + new URLSearchParams({method:method.id});
    footer.append(create, samples); card.append(details, footer); host.append(card);
  }
  const buttons = [...document.querySelectorAll('[data-flow-filter]')];
  const cards = [...document.querySelectorAll('[data-flow-category]')];
  const status = document.getElementById('workflow-filter-status');
  const search = document.getElementById('workflow-search');
  let currentFilter = 'all';

  function select(filter, remember = false) {
    const selected = buttons.find(button => button.dataset.flowFilter === filter) || buttons[0];
    filter = selected.dataset.flowFilter;
    currentFilter = filter;
    const query = search.value.trim().toLocaleLowerCase();
    for (const button of buttons) button.setAttribute('aria-pressed', String(button === selected));
    let visible = 0;
    for (const card of cards) {
      card.hidden = (filter !== 'all' && card.dataset.flowCategory !== filter) || !String(card.dataset.search || card.textContent).toLocaleLowerCase().includes(query);
      if (!card.hidden) visible++;
    }
    for (const section of document.querySelectorAll('[data-workflow-section]')) section.hidden = !section.querySelector('[data-flow-category]:not([hidden])');
    status.textContent = `${visible} 项 · ${selected.textContent}${query ? ' · 已筛选' : ''}`;
    document.getElementById('workflow-empty').hidden = visible > 0;
    document.getElementById('workflow-clear').hidden = !query && filter === 'all';
    if (remember) {
      const url = new URL(location.href);
      if (filter === 'all') url.searchParams.delete('category');
      else url.searchParams.set('category', filter);
      if (query) url.searchParams.set('q', search.value.trim()); else url.searchParams.delete('q');
      url.hash = '';
      history.replaceState(null, '', url.pathname + url.search);
    }
  }

  for (const button of buttons) button.addEventListener('click', () => select(button.dataset.flowFilter, true));
  search.addEventListener('input', () => select(currentFilter, true));
  document.getElementById('workflow-clear').onclick = () => { search.value = ''; select('all', true); search.focus(); };
  search.value = new URLSearchParams(location.search).get('q') || '';
  const target = cards.find(card => '#' + card.id === location.hash);
  const initial = new URLSearchParams(location.search).get('category') || target?.dataset.flowCategory || 'all';
  select(initial);
})();
