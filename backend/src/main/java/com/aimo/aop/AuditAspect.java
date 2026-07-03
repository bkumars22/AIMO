package com.aimo.aop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

import java.time.Instant;

@Aspect
@Component
public class AuditAspect {

    private static final Logger audit = LoggerFactory.getLogger("AUDIT");

    // Intercept all mutating controller methods
    @AfterReturning(
        pointcut = "execution(* com.aimo.controller..*(..)) && ("
                 + "@annotation(org.springframework.web.bind.annotation.PostMapping) || "
                 + "@annotation(org.springframework.web.bind.annotation.PutMapping) || "
                 + "@annotation(org.springframework.web.bind.annotation.PatchMapping) || "
                 + "@annotation(org.springframework.web.bind.annotation.DeleteMapping))",
        returning = "result"
    )
    public void logMutation(JoinPoint jp, Object result) {
        String user = "anonymous";
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.getPrincipal() instanceof String s) {
            user = s;
        }
        audit.info("AUDIT user={} method={} timestamp={}",
                user, jp.getSignature().toShortString(), Instant.now());
    }
}
