package tools.gsbatch;

/** 一条决策：续不续、不续的理由、退避秒数。 */
public class Decision {

        public final boolean resume;
        public final String gaveUp;
        public final double wait;
        public Decision(boolean resume, String gaveUp, double wait) {
            this.resume = resume; this.gaveUp = gaveUp; this.wait = wait;
        }
    }
