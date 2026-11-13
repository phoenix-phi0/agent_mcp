package tools.gsbatch;

/** 一次 goose 进程结束后的现场（DRL 的事实）。
 *  从 GsbatchDecide 拆出来：DRL 在 tools.gsbatch 包里，默认包的类
 *  没法 import——第一版就因为 POJO 留在默认包整包编译失败。 */
public class Attempt {

        private String reason = "";
        private boolean transientErr;
        private String why;
        private int rc;
        private boolean hasComplete;
        private int retries;
        private boolean hasSession;
        private boolean cancelled;
        private double secondsLeft;
        private double[] backoff = {30, 60, 120};
        private int resumeMax = 3;
        private boolean decided;

        public String getReason() { return reason; }
        public void setReason(String v) { this.reason = v; }
        public boolean isTransient() { return transientErr; }
        public void setTransient(boolean v) { this.transientErr = v; }
        public String getWhy() { return why; }
        public void setWhy(String v) { this.why = v; }
        public int getRc() { return rc; }
        public void setRc(int v) { this.rc = v; }
        public boolean isHasComplete() { return hasComplete; }
        public void setHasComplete(boolean v) { this.hasComplete = v; }
        public int getRetries() { return retries; }
        public void setRetries(int v) { this.retries = v; }
        public boolean isHasSession() { return hasSession; }
        public void setHasSession(boolean v) { this.hasSession = v; }
        public boolean isCancelled() { return cancelled; }
        public void setCancelled(boolean v) { this.cancelled = v; }
        public double getSecondsLeft() { return secondsLeft; }
        public void setSecondsLeft(double v) { this.secondsLeft = v; }
        public double[] getBackoff() { return backoff; }
        public void setBackoff(double[] v) { this.backoff = v; }
        public int getResumeMax() { return resumeMax; }
        public void setResumeMax(int v) { this.resumeMax = v; }
        public boolean isDecided() { return decided; }
        public void setDecided(boolean v) { this.decided = v; }
    }
