package com.kcpilot;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class BackendApplicationTests {

    // 테스트 시작 시 pgvector 포함 PostgreSQL 컨테이너를 띄운다.
    // @ServiceConnection이 이 컨테이너의 접속 정보(url/user/password)를
    // Spring DataSource에 자동으로 주입하므로 별도 설정이 필요 없다.
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>(
            DockerImageName.parse("pgvector/pgvector:0.8.2-pg18")
                    .asCompatibleSubstituteFor("postgres"));

    @Test
    void contextLoads() {
    }

}
