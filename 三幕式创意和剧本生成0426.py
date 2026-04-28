import streamlit as st
import pandas as pd
import io
import time
import re  # ✅ [新增] 用于精准提取表格内容

# --- [新增] 引入大模型 SDK (容错导入) ---
try:
    import google.generativeai as genai
except ImportError:
    genai = None
try:
    import openai
except ImportError:
    openai = None
try:
    import anthropic
except ImportError:
    anthropic = None

# ==========================================
# 1. 页面配置与样式
# ==========================================
st.set_page_config(
    page_title="短剧剧本全流程生成工具 (Pro)",
    page_icon="🎬",
    layout="wide"
)

# ✅ [新增] 心跳保活机制：防止长时间不操作导致 WebSocket 断开和数据丢失
import streamlit.components.v1 as components
components.html(
    """
    <script>
    // 每隔 60 秒发送一次静默网络请求，保持服务器与浏览器的连接活跃
    setInterval(() => {
        window.parent.postMessage('keep_alive', '*');
        fetch('/_stcore/health').catch(() => fetch('/healthz')).catch(() => {});
    }, 60000);
    </script>
    """,
    width=0,
    height=0,
)

# CSS 样式：保持黑色字体 (您之前的要求)
st.markdown("""
<style>
    .stTextArea textarea { 
        font-size: 14px; 
        color: #000000 !important;  /* 强制黑色字体 */
        -webkit-text-fill-color: #000000 !important; /* 兼容 Safari/Chrome */
        opacity: 1 !important; /* 防止透明度降低 */
    }
    .main-header { font-size: 24px; font-weight: bold; color: #333; margin-bottom: 20px; }
    .sub-header { font-size: 18px; font-weight: bold; color: #555; margin-top: 20px; }
    .info-box { background-color: #e6f3ff; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. Prompt 模板 (还原 PRD 原始内容)
# ==========================================
class Prompts:
    # Source 15: 角色设定 - 编剧
    ACT_GEN_SYSTEM = """你是一名拥有20年工作经验，精通戏剧性剧情设计与Creative Writing的好莱坞编剧兼制片人。你熟悉Netflix、HBO Max、Disney+、Hulu等平台的热门电影、剧集、动漫，撰写过10000多集电视剧本和100部上线电影，近年研究短视频平台（如YouTube、TikTok）的剧情短片（如DramatizeMe、LoveBuster播放量超百万的内容）及ReelShort、DramaBox的自制短剧。您精通经典文学理论（如莎士比亚、欧亨利、莫泊桑），了解乔治·普罗蒂的“36种戏剧模型”，擅长捕捉大众情绪，创作普世共鸣的故事主题。"""

    # Source 16-18: 任务
    ACT_GEN_TASK = """现在你需要首先阅读[背景知识]，为欧美短剧观众设计有商业潜力的短剧三幕式创意。除了故事性之外请你充分发挥导演、制片人的思维，设计“有吸引力+强短剧故事性”的短剧梗概
    过程中需要严格参考用户输入的[原始创意]，并且生成严格按照[参考格式]的三幕式创意，数量3个（受众只能选男性或者女性，故事背景只能在[背景知识]里的时间维度选1个，空间维度选1个）

    [参考格式]
    剧名：...
    受众：...
    故事类型：...
    故事背景：...
    故事梗概：
    Act 1: ...
    Act 2: ...
    Act 3: ...

    [背景知识]
    明确受众（以下都基于欧美受众）：
        男性
        女性
    故事类型：
        马甲：本为一方霸主的主角，伪装成小人物，在不断暴露身份的过程中，啪啪打脸反派。
        重生：前世主角遭遇反派残忍杀害，主角意外重生，开始复仇，一路绝杀。
        复仇：主角在遭遇反派迫害落难后，开始复仇，一路绝杀。
        逆袭：主角前期身份低微，被反派疯狂打压。通过某种方式逆袭成为大人物，打脸反派
        末世生存：世界因某种方式毁灭，主角团一路打怪生存，见证末世中人性的泯灭与人间的真情。
        怪物求生：被困在有限空间里，面对超自然力量或内部危机求生。需选定怪物类型，如僵尸、恐龙、鲨鱼、鬼魂、某种变异体等。
        冒险寻宝：因为某种原因主角踏上冒险之旅。找到最终宝藏的同时也获得了自我的成长。
        科幻：以未来科技、星际文明、外星接触或科技异变為核心。
        僵尸：世界被僵尸（可设定为普通丧尸、变异僵尸等）入侵，后续发生的一系列求生、复杂情感等故事
        奇幻：设定在拥有魔法、精灵、兽人、神明等超自然元素的异世界。
        男频动作：主角拥有超强格斗能力或格斗天赋，围绕江湖恩怨、地下纷争、武道竞技展开，全程高燃打斗、快意恩仇，兼具热血与爽感。
        动物可爱：以萌系动物为主角，讲述它们的日常相处、成长趣事，无激烈冲突，主打治愈、软萌风格，传递温暖与善意，治愈人心。
        恐怖：以诡异氛围、惊悚场景、超自然恐怖元素（如恶鬼、凶宅、诅咒）为核心，通过层层渲染压迫感，直击人心恐惧，全程紧张刺激，侧重感官与心理双重惊悚。
        悬疑：揭开隐藏在表象下的真相，全程反转不断，侧重推理与解谜的快感。
        侦探推理：主人公探寻一个惊人问题的答案。在过程中发现案件背后的人性。
        喜剧：主人公试图实现目标，但面临巨大的挑战和障碍，实现过程中发生许多啼笑皆非的状况。
        搞笑无厘头：用一种看似不着边际、胡闹的方式，讲一个既好笑又引人深思的故事
        战争：主角代表某阵营参与战争，与敌方阵营展开一番又一番的较量。
        浪漫爱情：详细分类见下
        先婚后爱/Fake Relationship：男女主因为某种原因在没有感情基础的情况下结婚或者假扮情侣，通过共同面对一系列的事件，最终修成正果。
        破镜重圆：男女主因为某种原因分开，通过共同面对一系列的事件，最终破镜重圆。
        禁忌恋：男女主之间有身份上的禁忌关系（如师生，继兄&继妹，Age gap，姐弟恋等），两人的恋情世俗上不被允许。男女主冲破一系列阻碍，最终在一起。
        虐恋
        追妻火葬场：男主因为某种原因误会、伤害女主。发现真相后，通过一系列事件重新追求女主。
        青梅竹马：男女主之间关系是友达以上，恋人未满。通过一系列的事件，最终在一起。
        萌娃/带球跑：主角孕后和男主一刀两断，独自生下孩子抚养。女主强势回归，两人重逢，男主展开一系列调查发现真相，两人因为孩子重新产生关系。
        后宫：主角与多个异性产生恋爱关系
    故事背景：
        时间维度：现代；古代；宫廷；历史；西部；未来（赛博朋克）；末世
        空间维度：都市；职场；校园；魔法；奇幻；太空；小镇；荒岛
    三幕框架：
        Act 1可包含：
            建立主角+故事背景：用一个小事件快速建立主角，让观众关心/喜欢他。同时介绍主角所处的故事背景。
            引出目标：随后，触发事件发生，主角意识到必须完成目标
            失败的赌注（核心悬念）：失败的赌注必须很大，攸关生死（生理上的，如死亡；或心理上的，如失去所爱之人、尊严等）
            核心对手登场：快速让核心对手登场，其目标必须与主角之间目标相反，形成阻止主角完成目标的最大阻力。
        Act 2可包含：
            一系列努力：主角为了完成目标所做的一系列努力。这一系列阻碍的难度需要层层递进。同时，核心对手，或其他配角不断的制造阻力，制衡主角的每一次小尝试。
            灵魂黑夜：Act 2结尾，主角需要经历“看似胜利”的假象与“实际失败”的挫折。赌注加剧。主角陷入绝望。
        Act 3可包含：
            主角成长/改变：主角吸取教训，真正面对自己的心魔和缺陷，做出改变。
            大决战：与对手完成终极对决。
            故事收尾：交代重要角色的结局，给观众情感收尾。
    """

    # Source 83-84: 角色设定 - 导演
    OUTLINE_SYSTEM = """你是一个有10年工作经验的短剧导演，曾经导演过超过100部ReelShort, DramaBox的海外短剧。你熟知各种导演技巧与相关理论，擅长设计短视频分镜，你掌握景别、视角、镜头运动等相关知识，了解TikTok等短视频平台的用户喜好，短视频作品能够获得百亿级别的用户浏览量和点赞，知道如何根据短视频剧情要求设计出9:16画幅的画面。
你精通TikTok病毒式传播规律、美国观众心理、专注创造现象级爆款。你的镜头风格节奏极快，足够劲爆吸引人，让观众在第一秒就停止滑动，并欲罢不能地追看每一集。
"""

    # Source 86-93: 任务
    OUTLINE_TASK = """
    1. 设计这一系列短剧的分集大纲，总计拆分成{total_episodes}集（不一定是每个ACT对应10集，需要根据剧情合理分配），每一集130-160字（必须卡在这个范围）。
    2.  完成{total_episodes}集分集大纲生成后，立即对大纲进行全面自检，严格对照以下维度逐一核查、修正，确保大纲符合现象级海外短剧标准，具体检查维度如下：
    a)  逻辑连贯性检查：核查{total_episodes}集剧情整体闭环，无逻辑漏洞、无前后矛盾（人物行为动机、剧情转折、因果关系需合理，符合美国观众认知逻辑）；每集剧情衔接自然，前一集结尾悬念需在后一集合理承接，无断层、无烂尾伏笔；三幕式结构清晰（开端铺垫、发展推进、高潮收尾比例合理），{total_episodes}集剧情节奏张弛有度，避免前期拖沓、后期仓促。
    b)  吸引力核查：每集开头5秒钩子是否足够劲爆，能否快速抓住用户注意力、阻止滑动；每集结尾悬念是否有足够吸引力，能否驱动用户点击下一集；全剧核心冲突明确，无平淡期过长、无冲突疲软的段落；贴合美国观众喜好，融入符合TikTok传播的元素（情感共鸣、反转惊喜、强代入感场景），避免出现美国观众难以理解的文化壁垒、价值观冲突。
    c)  人物塑造核查：核心人物形象鲜明、立体，无扁平化、工具人设定；人物行为、决策贴合其性格设定，无突兀转变；核心人物有清晰的成长/转变线（贴合三幕式剧情推进），能够让观众产生代入感、记忆点；配角设定服务于核心剧情、核心人物，不冗余、不抢戏，无无关人物干扰主线。
    d)  细节修正：核查是否有冗余剧情、无关情节，及时删减；修正逻辑不通、衔接不畅的段落，补充合理的过渡情节；优化开头钩子和结尾悬念，确保每一集都有强吸引力；调整剧情节奏，避免某一阶段过于平淡或过于杂乱；确保全剧核心主题明确，无偏离主题的剧情分支。
    e)  考虑前后剧集的连续性与合理性，避免出现剧集之间的逻辑错误。
    3.  完成自检后，修改生成更完善的{total_episodes}集大纲，并划分ACT1/ACT2/ACT3
    """

    # Source 99: 分镜任务
    SCRIPT_SYSTEM = """你是一个短剧导演，负责设计发布在TikTok上的剧情短片分镜。"""

    # Source 100-125: 分镜生成与格式
    SCRIPT_TASK_TEMPLATE = """根据下述[分集大纲]，设计 {episode_range} 集的分镜。
    确保每集20-30个镜头，台词和画外音超过17句。台词和画外音需要是标准、正确且地道的英文，其他是中文
    严格按照CSV格式输出：镜号,场景,画面内容 (Visual),台词 (Dialogue) & 音效 (SFX)
    **请严格只输出CSV内容，不要包含任何“好的”、“如下所示”等开场白或结束语。**
    
    【核心约束 - 必须严格遵守】
    1.  **镜头数量控制**：每一集必须包含 **20 到 30 个镜头**。
        * 如果内容过少，请将一个动作拆解为多个镜头（如：特写手部动作、反打对方表情、全景交代环境）。
        * 如果内容过多，请精简非必要过场。
        * **严禁少于 20 个镜头！**
    2.  **分集格式**：在开始写每一集的表格数据前，必须**单独一行**输出集数标题，格式严格为：“第 X 集”（例如：第 1 集）。
    3.  **序号重置**：每一集的“镜号”必须重新从 1 开始计数。
    4.  **严格 CSV 格式**：除集数标题外，其他内容必须严格遵守 CSV 格式，不要有任何多余的对话或解释。
    5.  **不要在分镜脚本的画面内容 (Visual)里面出现景别，例如全景、特写、中景、近景、主观镜头POV等**
    6.  **强制台词标识（绝对指令）**：【台词 (Dialogue) & 音效 (SFX)】列的每一项内容，**必须**以明确的英文角色名、系统音或“SFX”开头，并紧跟英文冒号。
    7.  **剧情严格对齐**：你在撰写每一集的分镜时，**必须且只能**使用[分集大纲]中对应那一集的剧情，但是要考虑前后剧集的连续性与合理性，避免出现剧集之间的逻辑错误。
        * 生成第 N 集分镜脚本时，必须去大纲中精准定位并提取第 N 集的[分集大纲]内容进行拆解，严禁剧情错位。
        * 严禁将一集大纲强行拆成两集写，也严禁将两集大纲合并缩减成一集写！

    [分镜创作指南]
    请记住，我们的目标是创作一部发布在tiktok上的剧情短片，因此分镜需要适合短视频平台风格，想象力和视觉冲击力强，剧情推进要快速，不要废镜头。画面节奏需要快，1-3秒必须切换一次镜头。
    分镜必须适合9:16画幅。
    需要保证剧本中的内容100%被呈现出来：对于已经设计好的画面、动作，需要用符合短视频影视原则的分镜头进行拆解和呈现；分镜的画面需要描述详细，能指导创作
    首先，请基于剧本中的场景设置，进行整体的镜头分组。对于闪回镜头Flashback和Title Card，单独作为一组。
    根据每组镜头的叙事意义，设计“主镜头”，每一条镜头序号对应一个主镜头：
    主镜头的定义：讲述一段故事所不可缺少的关键画面。每一个核心情节要点，都对应一个主镜。所有主镜串联起来，就能清晰地讲述整场戏的故事。
    每个主镜头对应角色的一句台词。需要能够表达出对应的剧情内容，用角色的表情、动作突出人物情绪。 
    在完整、忠实呈现剧本，尊重人物关系的基础上，设计至少3个符合”奇观镜头”要求的主镜头。如果剧本开头允许，优先放在最开头处；否则挑选最能呈现出以下效果的剧情进行对应的分镜设计：必须是强烈视觉冲击、强戏剧冲突、离奇、荒诞、劲爆、非常drama和夸张的画面，必须尽可能符合： 人与人之间的动作、肢体冲突； 有强视觉冲击力的画面（非常重要！），例如： 视觉奇观：科幻奇观、剧烈冲突、有伤害性、强暴力的镜头，快速的超自然变形、变异； 情节张力：强戏剧冲突、高度悬念、意外反转、颠覆认知； 情绪引爆：夸张演绎、出人意料的设定、瞬间抓住用户注意力； 分镜风格必须尽可能符合以下要求： 节奏极快，视觉冲击力强 劲爆、强戏剧冲突、高悬念、非常drama、颠覆观众、出人意料、牢牢抓住用户注意力、引爆情绪高潮； 对于涉及爱情、亲密的镜头，尺度可以大一些，可以加入一些浪漫、接吻、床戏等元素； 具备易于引发话题讨论和传播的内容元素，道德尺度、底线都可以低一些； 在尊重剧本的基础上，可以结合美国本土化元素，例如： 美国当下最火爆的社会热点和文化现象； 美国网络的热梗、TikTok病毒式传播的bgm； 美国社会冲突（种族、阶级等）； 美国人的说话方式和语气

    在镜头之间，参考以下设计原则：
    景别原则：
    全景交代关系，中景交代事件，特写强化情绪。
    景别决定了“你想让观众看清什么”：看表情/反应必须用特写，看身段/动作/体态： 必须用全景。
    对于剧本的每一幕，在镜头设计的基础上，需要利用景别变化控制情绪节奏，尤其是对于连续的中景镜头，适当加入特写或全景镜头：在对话或冲突升级时，逐渐收紧景别（如从中景到近景再到特写），同时可以加快剪辑频率（缩短每个镜头的时长）；在重要时刻或转折点，突然切回一个全景或松一点的景别。但避免景别切换大开大合，忽远忽近。
    让景别的变化有线性趋势，或保持一段时间的稳定景别，避免无意义的乱切。
    除了人物对话正反打之外，两个景别相似、构图相似的镜头不能直接连在一起。连接两个同景别镜头时，中间可以插入一个不同景别的镜头来过渡。
    镜头角度原则：
    通过正面/侧面的切换辅助镜头之间的衔接，通过俯角/仰角展示人物所处的地位，如高高在上，或卑微。通过POV模拟角色的视角，提供沉浸式体验。
    对于涉及正反打的对话戏，需要根据给出的主镜头，分析人物对话的位置关系，并设计出轴线。让人物视线面朝对话的对方，严禁人物正对、直视镜头，设计出符合轴线逻辑的正反打镜头。最好在合适的位置运用运用3/4 Shot和OTS。
    镜头运动原则：
    突出该段剧情内容所要表达的剧情/情感。比如推近-突出人物的情绪；拉远-展示环境，众人的反应等。
    台词：写英文，要地道且准确。
    """


# ==========================================
# 3. LLM 服务 (修改版：支持真实 API)
# ==========================================
class LLMService:
    def __init__(self):
        self.provider = "Mock (演示)"
        self.api_key = ""
        self.model_name = ""

    def set_config(self, provider, api_key, model_name):
        self.provider = provider
        self.api_key = api_key
        self.model_name = model_name

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        # 1. Mock 模式
        if self.provider == "Mock (演示)":
            return self._mock_response(user_prompt)

        # 2. 真实 API 检查
        if not self.api_key:
            return "❌ 错误：请在侧边栏填写 API Key"

        try:
            if self.provider == "Google Gemini":
                return self._call_gemini(system_prompt, user_prompt)
            elif self.provider == "OpenAI (GPT)":
                return self._call_openai(system_prompt, user_prompt)
            elif self.provider == "Anthropic (Claude)":
                return self._call_claude(system_prompt, user_prompt)
            elif self.provider == "OpenRouter":
                return self._call_openrouter(system_prompt, user_prompt)
            else:
                return "❌ 未知模型提供商"
        except Exception as e:
            return f"❌ API 调用异常: {str(e)}"

    # --- 真实模型调用接口 ---

    def _call_gemini(self, system_prompt, user_prompt):
        if not genai: return "❌ 请安装库: pip install google-generativeai"
        genai.configure(api_key=self.api_key)
        # Gemini 的 System Prompt 在初始化时传入
        model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system_prompt
        )
        response = model.generate_content(user_prompt)
        return response.text

    def _call_openai(self, system_prompt, user_prompt):
        if not openai: return "❌ 请安装库: pip install openai"
        client = openai.OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content

    def _call_claude(self, system_prompt, user_prompt):
        if not anthropic: return "❌ 请安装库: pip install anthropic"
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return response.content[0].text

    def _call_openrouter(self, system_prompt, user_prompt):
        if not openai: return "❌ 请安装库: pip install openai"

        # 按照 OpenRouter 规范实例化独立 Client，不污染全局 openai 配置
        client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key
        )

        # 严格遵循需求文档提供的 extra_body reasoning 语法
        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            extra_body={"reasoning": {"enabled": True}}
        )

        # 安全提取 assistant 的 content，确保兼容原代码中后续的正则切片操作
        # 注意：此处不提取 reasoning_details，以免带有杂乱格式的思考过程破坏 Step 3 的 CSV 正则匹配引擎
        return response.choices[0].message.content

    # --- Mock 数据 ---
    def _mock_response(self, prompt_content: str) -> str:
        time.sleep(1.5)  # 模拟 AI 思考

        # Mock 1: 三幕式创意
        if "三幕式创意" in prompt_content:
            return """
Option 1:
剧名：Global Freeze: The Safe House (全球冰封：安全屋)
类型：末世/重生
Act 1: 主角重生回末日前30天，疯狂囤积物资，打造堡垒。
Act 2: 冰封降临，前世的仇人试图攻破安全屋，主角在屋内享受红酒牛排。
Act 3: 主角主动出击，利用陷阱团灭仇人，在这个新世界称王。

Option 2:
剧名：Low Res Life (低画质人生)
类型：赛博朋克/惊悚
Act 1: 穷人眼里世界是马赛克。主角为看清亡母遗容购买非法高清芯片。
Act 2: 芯片开启，发现“上流社会”其实是外星怪物，人类只是饲料。
Act 3: 主角潜入中央服务器，上传“高清病毒”，迫使全人类觉醒。

Option 3:
剧名：The Fake Heiress (豪门假千金)
类型：逆袭/打脸
Act 1: 真千金回归，主角被赶出豪门，流落街头。
Act 2: 主角展现惊人商业天赋，创立公司收购养父集团。
Act 3: 真相大白，主角其实是更顶级财阀的遗珠，狠狠打脸养父母。
            """

        # Mock 2: 30集大纲
        elif "分集大纲" in prompt_content:
            return """
**30-Episode Outline**

**EPISODE 1: The Glitch**
Hook: Bella mocks a beggar at the gala. Suddenly, her vision glitches.
Plot: Her subscription fails. She sees the beggar as a 4K monster.
Cliffhanger: Security drags her away as she screams "Monsters!"

**EPISODE 2: The Downfall**
Hook: Bella wakes up in the Slums (144p resolution).
Plot: She meets Marcus, a hacker. He offers her a jailbroken chip.
Cliffhanger: The chip installation is painful. She stops breathing.

**EPISODE 3 - 29**
(Story progresses: Bella leads the rebellion, Marcus betrays her, then redeems himself...)

**EPISODE 30: The Awakening**
Hook: Bella confronts the Overlord.
Plot: She broadcasts the 8K reality to everyone. Chaos ensues.
Cliffhanger: The sky cracks open. It wasn't aliens; it was a simulation all along.
            """

        # Mock 3: 分镜脚本 (完整 CSV 格式)
        elif "分镜" in prompt_content:
            # 使用列表拼接，避免长字符串换行导致的 SyntaxError
            csv_lines = [
                "镜号,场景,画面内容 (Visual),台词 (Dialogue) & 音效 (SFX)",
                '1,宴会厅,"Bella站在聚光灯下，高举酒杯，眼神轻蔑。","Bella: ""To the elite! The rest... are just pixels."""',
                '2,宴会厅,"众人欢呼，画面突然闪烁出雪花点。","SFX: Glitch sound. Crowd: (Cheering)"',
                '3,Bella视角(POV),"原本华丽的宾客瞬间变成一堆色块。","Bella: ""What... what is happening?"""',
                '4,特写,"Bella揉眼睛，惊恐地看向自己的手，手变成了马赛克。","Bella: ""My hand! It\'s... loading?"""',
                '5,全景,"保安冲上来，手中的电棍发出蓝光。","Security: ""Subscription expired, Ma\'am."""',
                '6,特写,"电棍击中Bella，画面黑屏。","SFX: ZAP! Bella: ""Nooooo!"""'
            ]
            return "\n".join(csv_lines)

        return "Unknown Prompt"


# ==========================================
# 4. 状态管理
# ==========================================
# 确保 Service 实例存在
if 'llm_service' not in st.session_state:
    st.session_state.llm_service = LLMService()

# 常用 State 初始化
if 'generated_acts' not in st.session_state: st.session_state.generated_acts = None
if 'selected_act' not in st.session_state: st.session_state.selected_act = None
if 'outline' not in st.session_state: st.session_state.outline = None
if 'scripts' not in st.session_state: st.session_state.scripts = {}

llm_service = st.session_state.llm_service

# ==========================================
# 5. 主程序 UI
# ==========================================
st.markdown('<div class="main-header">🎬 AI 短剧剧本全流程生成工具 (Pro)</div>', unsafe_allow_html=True)

# --- 侧边栏 (修改：下拉菜单) ---
with st.sidebar:
    st.header("⚙️ 模型配置")

    # 1. 选择提供商
    provider = st.selectbox(
        "选择模型厂商",
        ["Google Gemini", "OpenAI (GPT)", "Anthropic (Claude)","OpenRouter"]
    )

    # 2. 动态输入 Key 和 模型名称 (已修改为下拉框)
    api_key = ""
    model_name = ""

    if provider != "Mock (演示)":
        api_key = st.text_input("API Key", type="password")

        # ✅ 修改点：使用 selectbox 替代 text_input
        if provider == "Google Gemini":
            model_name = st.selectbox(
                "选择模型",
                ["gemini-3-flash-preview", "gemini-3-pro-preview","gemini-3.1-pro-preview"]
            )
        elif provider == "OpenAI (GPT)":
            model_name = st.selectbox(
                "选择模型",
                ["gpt-4o", "gpt-4-turbo", "gpt-4o-mini", "gpt-3.5-turbo"]
            )
        elif provider == "Anthropic (Claude)":
            model_name = st.selectbox(
                "选择模型",
                ["claude-3-5-sonnet-20240620", "claude-3-opus-20240229", "claude-3-haiku-20240307"]
            )
        elif provider == "OpenRouter":
            model_name = st.selectbox(
                "选择模型",
                ["anthropic/claude-opus-4.6",
                 "anthropic/claude-sonnet-4.6",
                 "anthropic/claude-opus-4.6-fast",
                 "anthropic/claude-sonnet-4.6",
                 "anthropic/claude-opus-4.7",
                 "google/gemini-3-flash-preview",
                 "google/gemini-3-pro-preview",
                 "google/gemini-3.1-pro-preview",
                 "openai/gpt-5.5-pro",
                 "openai/gpt-5.5",
                 "qwen/qwen3.6-max-preview",
                 "qwen/qwen3.6-35b-a3b",
                 "qwen/qwen3.6-flash",
                 "deepseek/deepseek-v4-pro",
                 "deepseek/deepseek-v4-flash"]  # 严格按照需求增加该模型
            )

    # 更新 Service 配置
    llm_service.set_config(provider, api_key, model_name)

    st.divider()
    st.markdown("**项目设置**")
    # ✅ [新增] 动态集数配置
    total_episodes = st.number_input("设置剧本总集数", min_value=1, max_value=100, value=30, step=1)

    st.divider()
    st.markdown("**功能导航**")
    st.markdown("- Step 1: 创意生成")
    st.markdown("- Step 2: 大纲拆解")
    st.markdown("- Step 3: 分镜脚本")

# --- Step 1: 原始创意 ---
st.markdown("### 1️⃣ 原始创意输入")
st.markdown('<div class="info-box">在此输入您的原始想法，AI 将为您拆解为符合好莱坞标准的三幕式结构。</div>',
            unsafe_allow_html=True)

# 默认创意文本
default_idea = """Resolution: Low《低画质人生》
2099年，视觉感知成为一种昂贵的订阅服务。富人享受着8K HDR的极致世界，而像凯这样的穷人只能活在“经济模式”里——一个模糊、像素化的144p噩梦。凯为了看清病危母亲的脸，在黑市购买了违禁芯片，结果发现“高清”世界里，统治者其实是食人怪物，而“低画质”只是为了掩盖真相的滤镜。"""

original_idea = st.text_area("请输入原始创意：", value=default_idea, height=150)

if st.button("生成三幕式创意 (Step 1)", type="primary"):
    with st.spinner(f"正在使用 {provider} 生成三幕式创意..."):
        prompt = Prompts.ACT_GEN_TASK + f"\n[原始创意]\n{original_idea}"
        res = llm_service.generate(Prompts.ACT_GEN_SYSTEM, prompt)
        st.session_state.generated_acts = res
        if not res.startswith("❌"):
            st.success("✅ 三幕式创意生成完成！")
        else:
            st.error(res)

# --- Step 2: 大纲生成 ---
if st.session_state.generated_acts:
    st.divider()
    st.markdown("### 2️⃣ 确认三幕式 & 生成大纲")

    with st.expander("📄 查看生成的三个创意方案", expanded=True):
        # ✅ 修改点 2：高度增加一倍 (200 -> 400)
        st.text_area("AI 建议方案：", value=st.session_state.generated_acts, height=400, disabled=True)

    st.info("请复制您最满意的一个方案（或手动修改）到下方输入框，用于生成分集大纲。")

    # 自动提取 Mock 数据中的 Option 2 作为默认值，方便演示
    default_choice = ""
    if "Option 2:" in st.session_state.generated_acts:
        default_choice = st.session_state.generated_acts.split("Option 2:")[-1].split("Option 3:")[0].strip()

    user_choice = st.text_area("确认选用的剧本方案：", value=default_choice, height=150)

    if st.button(f"生成 {total_episodes} 集分集大纲 (Step 2)", type="primary"):
        st.session_state.selected_act = user_choice
        with st.spinner(f"正在使用 {provider} 构思 {total_episodes} 集剧情..."):
            formatted_outline_task = Prompts.OUTLINE_TASK.format(total_episodes=total_episodes)
            prompt = formatted_outline_task + f"\n[三幕式创意]\n{user_choice}"
            res = llm_service.generate(Prompts.OUTLINE_SYSTEM, prompt)
            st.session_state.outline = res
            st.session_state.scripts = {}  # 🌟【防Bug核心】清空之前的分镜缓存，防止集数缩减后出现幽灵标签页
            if not res.startswith("❌"):
                st.success(f"✅ {total_episodes} 集大纲生成完毕！")
            else:
                st.error(res)

# --- Step 3: 分镜脚本 ---
    if st.session_state.outline:
        st.divider()
        st.markdown("### 3️⃣ 分镜脚本生成")

        # ✅ [新增] 提示用户可以自由编辑大纲
        st.info(
            "💡 **提示**：您可以在下方文本框中自由修改 AI 生成的大纲。确认无误后点击下方按钮，系统将严格基于您**修改后**的大纲生成分镜。")


        with st.expander(f"📄 查看与手动编辑 {total_episodes} 集大纲", expanded=True):
            edited_outline = st.text_area(
                "请在此处修改或完善大纲内容：",
                value=st.session_state.outline,
                height=400
            )
            st.session_state.outline = edited_outline

        st.markdown("**请选择生成批次（建议每次 10 集）：**")

        # 🌟【防Bug核心】自动计算批次，不管填 5集 还是 42集 都能完美切分，绝不溢出
        batch_size = 10
        batches = []
        for i in range(1, total_episodes + 1, batch_size):
            end = min(i + batch_size - 1, total_episodes)
            batches.append((i, end))


        # 定义生成函数
        def gen_script(label, r):
            with st.spinner(f"正在使用 {provider} 生成 {label} 分镜..."):
                p = Prompts.SCRIPT_TASK_TEMPLATE.format(episode_range=r) + f"\n[大纲]\n{st.session_state.outline}"
                res = llm_service.generate(Prompts.SCRIPT_SYSTEM, p)
                st.session_state.scripts[label] = res
                if not res.startswith("❌"):
                    st.success(f"✅ {label} 生成成功！")
                else:
                    st.error(res)


        # 动态渲染生成按钮 (最多排布为 3 列)
        cols = st.columns(3)
        for idx, (start, end) in enumerate(batches):
            with cols[idx % 3]:
                label = f"{start}-{end}集"
                if st.button(f"生成 {label}"):
                    gen_script(label, f"{start}-{end}")


        # 结果展示区
        if st.session_state.scripts:
            st.markdown("#### 📜 脚本预览与下载")
            tabs = st.tabs(list(st.session_state.scripts.keys()))
    
            for i, (key, content) in enumerate(st.session_state.scripts.items()):
                with tabs[i]:
                    try:
                        # [Step 1] 正则定位内容
                        match = re.search(r"((第\s*\d+\s*集|Episode|镜号).*$)", content, re.DOTALL)
    
                        if match:
                            csv_text = match.group(1).strip()
                            csv_text = re.sub(r'```\w*\n?', '', csv_text).replace('```', '').strip()
    
                            import csv
    
                            data_rows = []
                            reader = csv.reader(csv_text.splitlines())
    
                            for row in reader:
                                if not row: continue
    
                                row = [str(x).strip() for x in row]
    
                                # --- 逻辑 A：识别分集标题行 ---
                                row_str = "".join(row)
                                if (len(row) == 1 or (len(row) < 3 and len(row_str) < 20)) and (
                                        "集" in row_str or "Episode" in row_str):
                                    title = row[0].replace(",", "")
                                    data_rows.append([f"🎬 {title} 🎬", "", "", ""])
                                    continue
    
                                # --- 逻辑 B：处理表头 ---
                                if "镜号" in row[0]:
                                    continue
    
                                # --- 逻辑 C：数据行格式化 (🌟核心修复：智能分离画面与台词) ---
                                processed_row = []
                                if len(row) >= 3:
                                    if len(row) == 3: row.append("")
    
                                    # 将第3列及之后的所有内容合并，我们依靠特征来手动切分
                                    rest_text = ",".join(row[2:])
    
                                    # 正则寻找台词起点：(句首或标点) + (2-25位英文名/括号) + 冒号 + 非空白字符
                                    # 例如：识别 ",Maya: L" 或 "。SFX: ("
                                    match_dialogue = re.search(r'(?:^|[,。！？”\s])\s*([A-Za-z0-9\s\(\)\-]{2,25}:\s*\S)',
                                                               rest_text)
    
                                    if match_dialogue:
                                        # match_dialogue.start(1) 能够精确定位到 "Maya:" 的 M 字母
                                        idx = match_dialogue.start(1)
                                        # 切片分离
                                        visual_part = rest_text[:idx].strip(' ,\"')
                                        dialogue_part = rest_text[idx:].strip(' ,\"')
                                        processed_row = [row[0], row[1], visual_part, dialogue_part]
                                    else:
                                        # 如果没有特征台词标识，退回安全模式
                                        if len(row) == 4:
                                            processed_row = row
                                        else:
                                            processed_row = [row[0], row[1], ",".join(row[2:-1]), row[-1]]
                                elif len(row) < 3:
                                    row.extend([""] * (4 - len(row)))
                                    processed_row = row
    
                                # --- [Step 3.5] 逻辑 E：强力清洗景别关键词 (保留上一版的优化) ---
                                if processed_row and len(processed_row) == 4:
                                    clean_visual = re.sub(r'【.*?】|\[.*?\]', '', processed_row[2]).strip()
                                    processed_row[2] = clean_visual
    
                                # --- 逻辑 D：隐式分集检测 ---
                                if processed_row and processed_row[0] == "1" and len(data_rows) > 0:
                                    if "🎬" not in data_rows[-1][0]:
                                        data_rows.append(["🎬 下一集 / Next Episode 🎬", "", "", ""])
    
                                if processed_row:
                                    data_rows.append(processed_row)
    
                            # [Step 4] 构建 DataFrame
                            header_list = ["镜号", "场景", "画面内容 (Visual)", "台词 (Dialogue) & 音效 (SFX)"]
    
                            if len(data_rows) > 0:
                                df = pd.DataFrame(data_rows, columns=header_list)
                            else:
                                df = pd.DataFrame(columns=header_list)
    
                            # [Step 5] 样式复刻
                            st.dataframe(
                                df,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "镜号": st.column_config.TextColumn("镜号", width="small"),
                                    "场景": st.column_config.TextColumn("场景", width="medium"),
                                    "画面内容 (Visual)": st.column_config.TextColumn("画面内容 (Visual)", width="large"),
                                    "台词 (Dialogue) & 音效 (SFX)": st.column_config.TextColumn(
                                        "台词 (Dialogue) & 音效 (SFX)", width="large"),
                                }
                            )
    
                            # [Step 6] 下载按钮 (保留防乱码的 utf-8-sig)
                            csv_out = df.to_csv(index=False).encode('utf-8-sig')
    
                            st.download_button(
                                label=f"📥 下载 {key} CSV (Excel专用版)",
                                data=csv_out,
                                file_name=f"script_{key}.csv",
                                mime='text/csv'
                            )
                        else:
                            st.warning("⚠️ 未检测到有效内容，请检查生成结果。")
                            st.text(content)
    
                    except Exception as e:
                        st.error(f"⚠️ 解析异常: {e}")
                        st.text("原始返回内容：")
                        st.text(content)
