package com.aimo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class AimoApplicationTests {

    @Test
    void contextLoads() {
        // Verifies the Spring context assembles without errors.
        // Phase 1 will add controller, service, and repository tests.
    }
}
