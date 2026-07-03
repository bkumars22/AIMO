package com.aimo.controller;

import com.aimo.entity.User;
import com.aimo.repository.UserRepository;
import com.aimo.security.JwtTokenProvider;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final UserRepository userRepo;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenProvider tokenProvider;

    public AuthController(UserRepository userRepo, PasswordEncoder passwordEncoder, JwtTokenProvider tokenProvider) {
        this.userRepo = userRepo;
        this.passwordEncoder = passwordEncoder;
        this.tokenProvider = tokenProvider;
    }

    record RegisterRequest(
        @Email @NotBlank String email,
        @NotBlank @Size(min = 8) String password
    ) {}

    record LoginRequest(
        @Email @NotBlank String email,
        @NotBlank String password
    ) {}

    @PostMapping("/register")
    public ResponseEntity<?> register(@Valid @RequestBody RegisterRequest req) {
        if (userRepo.existsByEmail(req.email())) {
            return ResponseEntity.status(HttpStatus.CONFLICT)
                    .body(Map.of("error", "Email already registered"));
        }
        var user = new User();
        user.setEmail(req.email());
        // Null guard: BCrypt is only called when password is non-null (learned from SCIP P0 bug)
        if (req.password() == null || req.password().isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("error", "Password required"));
        }
        user.setPasswordHash(passwordEncoder.encode(req.password()));
        user.setRole(User.Role.PIPELINE_OWNER);
        userRepo.save(user);
        String token = tokenProvider.generate(user.getEmail(), user.getRole().name());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("token", token, "email", user.getEmail(), "role", user.getRole()));
    }

    @PostMapping("/login")
    public ResponseEntity<?> login(@Valid @RequestBody LoginRequest req) {
        var user = userRepo.findByEmail(req.email()).orElse(null);
        // Null guard before BCrypt to avoid NullPointerException
        if (user == null || user.getPasswordHash() == null
                || !passwordEncoder.matches(req.password(), user.getPasswordHash())) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("error", "Invalid credentials"));
        }
        String token = tokenProvider.generate(user.getEmail(), user.getRole().name());
        return ResponseEntity.ok(Map.of(
                "token", token,
                "email", user.getEmail(),
                "role", user.getRole()
        ));
    }

    @PostMapping("/refresh")
    public ResponseEntity<?> refresh(@RequestHeader("Authorization") String authHeader) {
        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("error", "Missing token"));
        }
        String oldToken = authHeader.substring(7);
        if (!tokenProvider.isValid(oldToken)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("error", "Invalid or expired token"));
        }
        var claims = tokenProvider.parse(oldToken);
        String newToken = tokenProvider.generate(claims.getSubject(), claims.get("role", String.class));
        return ResponseEntity.ok(Map.of("token", newToken));
    }
}
