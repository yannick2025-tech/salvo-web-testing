import asyncio
import logging
import os

# 读取项目根目录的 .env（DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL）
from dotenv import load_dotenv

load_dotenv()

# 关闭默认扩展自动下载（uBlock Origin / cookie 屏蔽）。
# 国内网络下载扩展源常超时导致卡在 "Downloading ... extension"、浏览器不弹出。
# 如需重新启用，删掉下面这行或设为 0。
os.environ["BROWSER_USE_DISABLE_EXTENSIONS"] = "1"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

# DeepSeek 专用 provider，避免被识别成 OpenAI
from browser_use.llm import ChatDeepSeek
from browser_use.browser.profile import BrowserProfile

# 弹窗自动关闭 + 元素操作记忆扩展
from browser_use_ext.integration import create_memory_agent


async def main():
    llm = ChatDeepSeek(
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        model="deepseek-v4-pro",     # 能力更强、JSON schema 更稳（flash 结构化输出不稳定，会 action schema 校验失败）
        temperature=0.0,
        # 必须为 False：deepseek 思考模式不支持 tool_choice，
        # browser-use Agent 依赖 tool_choice 做结构化工具调用。
        thinking=False,
    )

    task = (
        # === 用例 0：登录（两个用例共用一次） ===
        "1. 打开登录页 https://uat-manhattan.shell.com.cn/Login 并等待加载完成。\n"
        "2. 在 placeholder 为『请输入您的账号』的输入框中填入用户名 18936879143。\n"
        "3. 在 placeholder 为『请输入您的密码』的输入框中填入密码 Abcd1234!@#$\n"
        "4. 点击『登录』按钮（HTML id 为 login）。\n"
        "5. 等待页面跳转和加载，判断是否登录成功：若页面出现后台/工作台/首页内容或不再停留在登录页，则登录成功。\n"

        # === 用例 1：充电订单管理，订单创建时间 = 过去 10 天(不含今天) ===
        "6. 在左侧菜单中找到并依次点击『订单管理』，在其展开的子菜单中点击『充电订单管理』，等待该页面加载完成。\n"
        "7. 在『充电订单管理』页面，找到『单据时间』下拉框（下拉默认显示『账单生成时间』），点击展开下拉后选择『订单创建时间』选项。\n"
        "8. 该页查询区的时间范围应设为『过去 10 天、不含今天』：即从昨天(今天往前1天)往前连续 10 个自然日 到 昨天。系统会自动把开始/结束日期设为正确值，因此请先检查『开始时间』与『结束时间』两个输入框：若它们显示的正是『过去 10 天(不含今天)』的窗口，就直接使用、不要改动、不要点开日历、不要重新输入；只有在它们明显不是该窗口时才需要修正。切勿用追加输入方式改动已有日期（会导致乱码）。\n"
        "9. 点击页面右上角的『查询』按钮，等待表格重新加载。\n"

        # === 用例 2：站点列表，二级城市选南京（不勾选一级江苏） ===
        "10. 在左侧菜单中找到『电站管理』（如果当前不是充电订单管理页面，可能需要回到首页或重新进入菜单），点击展开后在其子菜单中点击『站点列表』，等待该页面加载完成。\n"
        "11. 在『站点列表』页面的查询区，找到『城市名称』级联下拉框（Element UI Cascader，目前可能已带有『南京市』这样的标签 chip），点击该下拉框展开级联面板。\n"
        "12. 在级联面板的左侧一级列表中，找到并把鼠标移到『江苏省』上（不要点击它的勾选框！只触发右侧二级面板展开）。右侧二级面板会显示江苏省下的城市（南京市、常州市等）。\n"
        "13. 在右侧二级面板中，勾选『南京市』的复选框。明确不要勾选一级『江苏省』的复选框——本次只需要南京市一个城市。勾选完成后点击级联面板外部或按 Esc 关闭下拉。\n"
        "14. 点击页面右上角的『查询』按钮，等待『电站列表』表格重新加载。\n"

        # === 最终总报告（务必极简，避免超长 JSON 导致解析失败） ===
        "15. 用中文输出最终结论，每个用例只写一句简短话，不要长篇描述：\n"
        "   - 用例1(充电订单管理)：是否成功(单据时间=订单创建时间、日期=过去10天不含今天、订单列表已加载)。\n"
        "   - 用例2(站点列表)：是否成功(江苏未勾选、南京已勾选、已加载南京市站点列表)。"
    )

    agent = create_memory_agent(
        task=task,
        llm=llm,
        config_path="./memory/config.json",    # 弹窗+记忆配置文件
        use_vision=False,            # DeepSeek 为纯文本模型，不支持视觉
        # 1) 不下载 uBlock/cookie 扩展（国内网络下载超时）
        # 2) 屏蔽 --extensions-on-chrome-urls 启动参数，
        #    避免 Chrome 弹出"您使用的是不受支持的命令行标记"警告横幅
        browser_profile=BrowserProfile(
            enable_default_extensions=False,
            ignore_default_args=[
                "--extensions-on-chrome-urls",
                "--disable-extensions-http-throttling",
                "--disable-default-apps",
            ],
        ),
        use_judge=False,           # 关闭 judge：省 token，且避免它因"无截图/程序自动设日期"误判任务失败
    )
    history = await agent.run()
    # 打印最终结果/报告（可选）
    print("\n===== Agent Result =====")
    print(history.final_result())


if __name__ == "__main__":
    asyncio.run(main())
