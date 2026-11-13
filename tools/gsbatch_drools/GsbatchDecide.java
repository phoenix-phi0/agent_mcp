import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.kie.api.KieServices;
import org.kie.api.builder.*;
import org.kie.api.runtime.KieContainer;
import org.kie.api.runtime.KieSession;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

/**
 * GSBatch 自动续接判定：stdin 收一条事实 JSON，stdout 回一条决策 JSON。
 *
 * 事实：{"why": null|"stall"|"timeout"|"cancel", "rc": 0, "error": "…",
 *        "has_complete": true, "retries": 1, "has_session": true,
 *        "cancelled": false, "seconds_left": 120.0,
 *        "backoff": [30,60,120], "resume_max": 3}
 * 决策：{"resume": true|false, "gave_up": "…", "wait": 30}
 *
 * 规则在 decide.drl，逻辑对照 tools/gsbatch.py::_run_one 的内联判定，
 * 两边必须同判（tests/test_gsbatch_rules.py 有对照）。
 */
import tools.gsbatch.Attempt;
import tools.gsbatch.Decision;

public class GsbatchDecide {

    // 与 tools/gsbatch.py 的 _TRANSIENT / _NOT_TRANSIENT 保持一致
    static final Pattern NOT_TRANSIENT = Pattern.compile(
            "\\b429\\b|rate.?limit|quota|insufficient|余额|额度|欠费|限流|too many requests|usage limit|"
                    + "\\b40[13]\\b|unauthori[sz]ed|forbidden|authenticat|api.?key|invalid.?key|鉴权|"
                    + "\\b1113\\b|\\b1301\\b|\\b1302\\b|\\b1304\\b|\\b1308\\b|context.?length|maximum context|prompt is too long|too long",
            Pattern.CASE_INSENSITIVE);
    static final Pattern TRANSIENT = Pattern.compile(
            "stream decode error|error decoding response body|network error|connection (reset|refused|closed|aborted)|"
                    + "reset by peer|broken pipe|unexpected eof|incomplete (message|chunked)|timed? ?out|timeout|"
                    + "\\b50[0234]\\b|bad gateway|service unavailable|gateway time|server error|overloaded|"
                    + "temporarily unavailable|error sending request|hyper::|reqwest",
            Pattern.CASE_INSENSITIVE);



    static boolean likeTransient(String err) {
        return TRANSIENT.matcher(err).find() && !NOT_TRANSIENT.matcher(err).find();
    }

    /** 按 Python 侧的规则构造 reason / transient 标记。 */
    static Attempt buildAttempt(JsonNode f) {
        Attempt a = new Attempt();
        String why = f.path("why").isNull() || f.path("why").isMissingNode()
                ? null : f.path("why").asText();
        a.setWhy(why);
        a.setRc(f.path("rc").asInt(0));
        a.setHasComplete(!f.path("has_complete").isMissingNode() && f.path("has_complete").asBoolean(false));
        a.setRetries(f.path("retries").asInt(0));
        a.setHasSession(f.path("has_session").asBoolean(false));
        a.setCancelled(f.path("cancelled").asBoolean(false));
        a.setSecondsLeft(f.path("seconds_left").asDouble(0));
        a.setResumeMax(f.path("resume_max").asInt(3));
        JsonNode bo = f.path("backoff");
        if (bo.isArray() && bo.size() > 0) {
            double[] xs = new double[bo.size()];
            for (int i = 0; i < bo.size(); i++) xs[i] = bo.get(i).asDouble();
            a.setBackoff(xs);
        }
        String error = f.path("error").asText("").trim();

        if ("stall".equals(why)) {
            a.setReason("流卡住：没有输出，已杀掉");
            a.setTransient(true);          // 卡流不做过滤，照 Python 的分支
        } else if (why == null && (a.getRc() != 0 || !error.isEmpty()) && !a.isHasComplete()) {
            String reason = error.isEmpty() ? ("退出码 " + a.getRc()) : error;
            a.setReason(reason);
            a.setTransient(likeTransient(reason));
        }
        // 其余情况 reason 留空 = Python 的 reason=None → 静默停止
        return a;
    }

    public static void main(String[] args) throws IOException {
        String factJson = new String(System.in.readAllBytes(), "UTF-8");
        JsonNode fact = new ObjectMapper().readTree(factJson);
        Attempt a = buildAttempt(fact);

        String drl;
        try (InputStream in = GsbatchDecide.class.getResourceAsStream("/decide.drl")) {
            drl = new String((in != null ? in
                    : Files.newInputStream(Path.of(args.length > 0 ? args[0] : "decide.drl"))).readAllBytes(), "UTF-8");
        }

        KieServices ks = KieServices.Factory.get();
        KieFileSystem kfs = ks.newKieFileSystem();
        kfs.write("src/main/resources/decide.drl", drl);
        KieBuilder kb = ks.newKieBuilder(kfs);
        kb.buildAll();
        Results res = kb.getResults();
        if (res.getMessages().size() > 0) {
            for (Message m : res.getMessages()) System.err.println("DRL: " + m.getText());
            System.exit(2);
        }
        KieContainer c = ks.newKieContainer(ks.getRepository().getDefaultReleaseId());
        KieSession s = c.newKieSession();
        List<Decision> emits = new ArrayList<>();
        s.setGlobal("emits", emits);
        s.insert(a);
        s.fireAllRules();
        s.dispose();

        if (emits.size() != 1) {
            System.err.println("规则应恰好给出一个决策，实际 " + emits.size());
            System.exit(3);
        }
        Decision d = emits.get(0);
        String waitTxt = (d.wait == Math.floor(d.wait) && !Double.isInfinite(d.wait))
                ? String.valueOf((long) d.wait) : String.valueOf(d.wait);
        String json = "{\"resume\": " + d.resume
                + ", \"gave_up\": \"" + d.gaveUp.replace("\"", "\\\"") + "\""
                + ", \"wait\": " + waitTxt + "}";
        System.out.println(json);
    }
}
