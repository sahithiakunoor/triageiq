"""
KB documents tailored to the actual Jira Issue Reports v1 dataset:
Apache Software Foundation, Spring Framework, JBoss, CodeHaus open source projects.
Tickets are developer-filed bug reports, feature requests, and tasks on Java/OSS software.
"""

from pathlib import Path

KB_DIR = Path("./data/kb")
KB_DIR.mkdir(parents=True, exist_ok=True)

DOCS = {

"bug_report_triage.txt": """
Bug Report Triage Guide for Open Source Projects

This guide covers how to triage incoming bug reports in Apache, Spring, and JBoss projects.

Step 1 - Verify reproducibility:
Ask the reporter for exact steps to reproduce. A bug that cannot be reproduced cannot be fixed.
Request: JDK version, OS, project version, minimal code snippet that demonstrates the issue.
If the reporter cannot reproduce consistently, label as 'Cannot Reproduce' and ask for more details.

Step 2 - Check if already reported:
Search existing issues before proceeding. Duplicate issues waste maintainer time.
Link the duplicate to the original issue and close with status 'Duplicate'.

Step 3 - Determine severity:
Blocker: prevents core functionality, no workaround exists, affects many users.
Critical: major feature broken but workaround exists.
Major: significant issue but limited impact.
Minor: cosmetic or edge case issue.
Trivial: typo, minor documentation issue.

Step 4 - Assign component and fix version:
Tag the correct component (e.g., core, web, security, data, messaging).
Assign a target fix version only if a maintainer has committed to fixing it.
Do not assign fix versions to unconfirmed bugs.

Step 5 - Request missing information:
If the report lacks reproduction steps, version info, or stack trace, add label 'Needs More Info'.
Close unresponsive issues after 30 days with no response from reporter.
""",

"java_exception_runbook.txt": """
Java Exception and Stack Trace Analysis Runbook

NullPointerException (NPE):
Most common Java exception. Indicates a variable is null when a method is called on it.
Request the full stack trace from the reporter. The line number in the trace points to the exact cause.
Common causes: uninitialized fields, missing null checks, incorrect Spring bean wiring.
Ask reporter: what version introduced this? Does it happen on every execution or intermittently?

ClassNotFoundException and NoClassDefFoundError:
Indicates a class is missing from the classpath at runtime.
Usually caused by incorrect dependency version or missing transitive dependency.
Ask for: pom.xml or build.gradle, full dependency tree (mvn dependency:tree), exact Java and build tool version.

OutOfMemoryError:
Java heap space exhausted. Common in batch processing or large dataset operations.
Request: JVM heap settings (-Xmx), memory profiler output if available, data volume being processed.
Workaround: increase heap with -Xmx4g or enable streaming instead of loading all data into memory.

ConcurrentModificationException:
Collection modified while being iterated. Thread safety issue.
Common in multi-threaded applications or when modifying a list inside a forEach loop.
Fix: use Iterator.remove(), CopyOnWriteArrayList, or synchronize access.

StackOverflowError:
Infinite recursion. Check for circular references in object graphs, especially with Hibernate/JPA entities.
In Spring: circular bean dependencies cause this. Use @Lazy injection to break the cycle.

Connection timeout and socket exceptions:
Network or database connectivity issue. Request: network configuration, firewall rules, database host settings.
Common in Apache HttpClient and Spring RestTemplate. Check connection pool settings and timeout values.
""",

"apache_project_guide.txt": """
Apache Software Foundation Project Standards

Issue types used in Apache projects:
- Bug: something that was working and is now broken, or behaves differently from documented behavior.
- New Feature: request to add functionality that does not currently exist.
- Improvement: enhancement to existing functionality without changing core behavior.
- Task: non-code work such as documentation, dependency updates, or refactoring.
- Sub-task: child task of a larger story or epic.
- Test: issue related to missing or failing automated tests.

Priority levels in Apache Jira:
- Blocker: completely blocks development or testing, no workaround. Must be fixed before release.
- Critical: severe impact on major functionality. Fix targeted for current release.
- Major: important issue but does not block release. Scheduled for next sprint.
- Minor: limited impact. Scheduled when bandwidth allows.
- Trivial: cosmetic only. Fix in next cleanup sprint.

Workflow states:
Open → In Progress → Resolved → Closed
Reopen is allowed if a fix is found to be incomplete.
Won't Fix is used when the behavior is by design or the effort does not justify the fix.

Component ownership:
Each Apache project component has designated committers. Tag the correct component to route to the right person.
Apache Kafka: core, clients, connect, streams, tools.
Apache Hadoop: hdfs, mapreduce, yarn, common.
Apache Spark: core, sql, mllib, streaming, graphx.
Apache Maven: core, plugins, surefire, compiler-plugin.
""",

"spring_framework_guide.txt": """
Spring Framework Issue Handling Guide

Spring Boot auto-configuration issues:
When a bean is not being created as expected, check auto-configuration order.
Enable debug logging: logging.level.org.springframework=DEBUG to see which auto-configurations are applied.
Check for conflicting beans using ApplicationContext.getBeanDefinitionNames().
Common issue: @ConditionalOnMissingBean not triggering because a bean with a different name exists.

Spring Security issues:
403 Forbidden errors: check SecurityFilterChain configuration for the URL pattern.
CSRF token errors: ensure CSRF token is included in POST requests from forms.
Method security not working: verify @EnableMethodSecurity is present on configuration class.
JWT authentication: check token expiry, signing key configuration, and filter order.

Spring Data and JPA issues:
LazyInitializationException: entity accessed outside of transaction scope. Use @Transactional or fetch eagerly.
N+1 query problem: use JOIN FETCH in JPQL query or @EntityGraph annotation.
Transaction not rolling back: ensure @Transactional is on a public method in a Spring-managed bean.
Schema not updating: check spring.jpa.hibernate.ddl-auto setting — use validate in production.

Spring MVC issues:
404 Not Found: check @RequestMapping path, context path configuration, and whether the controller is scanned.
Serialization errors: check Jackson configuration for date format, null handling, and custom serializers.
File upload failures: configure spring.servlet.multipart.max-file-size and max-request-size.

Dependency injection issues:
UnsatisfiedDependencyException: a required bean is not found. Check component scan base package.
Circular dependency: use @Lazy on one of the dependencies to break the cycle.
""",

"build_and_dependency_guide.txt": """
Build Tools and Dependency Management Guide

Maven common issues:
Build failure with 'Could not resolve dependencies': check repository configuration in settings.xml.
Run mvn dependency:tree to see full dependency graph and identify version conflicts.
Use mvn enforcer:enforce to detect duplicate dependencies or version conflicts.
Local repository corruption: delete ~/.m2/repository/[groupId] and re-download.
Snapshot versions: use -U flag to force update of snapshot dependencies from remote repository.

Gradle common issues:
Gradle daemon issues: run ./gradlew --stop then retry the build.
Dependency resolution failure: check repositories block in build.gradle, ensure mavenCentral() is included.
Version conflicts: use configurations.all { resolutionStrategy.failOnVersionConflict() } to detect early.
Build cache issues: run ./gradlew clean to force full rebuild.

Dependency version conflicts (all build tools):
When two libraries require different versions of the same transitive dependency, the higher version typically wins.
This can cause NoSuchMethodError if an older API is expected. Pin the specific version explicitly.
Common conflict: different Spring components requiring different versions of spring-core.

Testing issues:
Test running out of memory: increase with -Xmx in MAVEN_OPTS or jvmArgs in Gradle test task.
Flaky tests: tests that pass and fail intermittently usually have timing dependencies or shared state.
Surefire plugin not finding tests: ensure test class name matches *Test.java or *Tests.java pattern.

Release and versioning:
Semantic versioning: MAJOR.MINOR.PATCH. Breaking changes require MAJOR bump.
SNAPSHOT versions are development builds not intended for production use.
Release versions are immutable — never redeploy a released artifact with the same version number.
""",

"code_review_standards.txt": """
Open Source Code Review and Contribution Standards

Pull request requirements for Apache and Spring projects:
- All pull requests must reference a Jira issue number in the title
- Tests must be included for bug fixes (regression test) and new features
- Documentation must be updated if public API changes
- Code style must match project conventions (checkstyle rules must pass)
- CI build must pass before review begins

Review process:
Two committer approvals required before merge in most Apache projects.
One committer approval required for minor fixes and documentation changes.
Reviewers check: correctness, test coverage, backward compatibility, performance implications.
A committer veto (-1) blocks the merge and requires discussion to resolve.

Backward compatibility:
Apache projects follow semantic versioning. Breaking changes require a major version bump.
Deprecated APIs must remain functional for at least one major version before removal.
Adding a new required parameter to a public method is a breaking change.
Adding an optional parameter with a default value is not a breaking change.

Documentation standards:
Public API methods must have Javadoc with @param, @return, and @throws.
New features require user-facing documentation in the project wiki or reference docs.
Configuration properties must be documented with type, default value, and description.

Common review feedback:
Missing null check on method parameter — add Objects.requireNonNull() or @NonNull annotation.
Test only covers happy path — add test cases for null input, empty collection, and boundary conditions.
Magic number in code — extract to named constant with clear meaning.
""",

"performance_profiling_guide.txt": """
Java Application Performance Profiling Guide

Identifying performance bottlenecks:
Use a profiler (VisualVM, JProfiler, async-profiler) to get CPU and memory flamegraphs.
High CPU: look for tight loops, inefficient algorithms, excessive string concatenation.
High memory: look for large collections, object creation in loops, memory leaks.

Common performance anti-patterns in Java:
String concatenation in loops: use StringBuilder instead of + operator inside a loop.
Repeated database calls: batch queries or use a cache (Spring Cache, Caffeine, Ehcache).
Unnecessary object creation: reuse objects where possible, especially in hot paths.
Blocking I/O on main thread: use async processing or thread pools for I/O operations.
Synchronization bottlenecks: minimize synchronized blocks, prefer concurrent collections.

JVM tuning for open source applications:
Heap sizing: start with -Xms and -Xmx set to the same value to avoid heap resizing pauses.
Garbage collection: G1GC is default in Java 9+. For low-latency, consider ZGC or Shenandoah.
GC logging: add -Xlog:gc* to see garbage collection activity and pauses.
Thread dump: use kill -3 [pid] on Linux or jstack [pid] to get thread dump for deadlock analysis.

Database query performance:
Use EXPLAIN ANALYZE in PostgreSQL to see query execution plan.
Missing index is the most common cause of slow queries. Add index on columns used in WHERE clauses.
Avoid SELECT * — specify only the columns you need.
Use connection pooling (HikariCP in Spring Boot) — never create a new connection per request.

Benchmarking:
Use JMH (Java Microbenchmark Harness) for accurate micro-benchmarks.
Warm up the JVM before measuring — first few executions are not representative due to JIT compilation.
Report results with confidence intervals, not just averages.
""",

"issue_resolution_patterns.txt": """
Common Issue Resolution Patterns in Open Source Projects

Pattern 1 - Cannot Reproduce:
Reporter provides insufficient information to reproduce the issue.
Response: Request minimum reproducible example, exact version numbers, OS, and JDK version.
If no response within 14 days, close with Cannot Reproduce and invite reporter to reopen with more details.

Pattern 2 - Works as Designed:
The reported behavior is intentional but not clearly documented.
Response: Explain the design decision, update documentation to clarify the behavior.
Close with Won't Fix but improve documentation so others do not hit the same confusion.

Pattern 3 - Duplicate Report:
The issue has already been reported in another ticket.
Response: Link to the original ticket, close as Duplicate. If the new report has better information, add it to the original.

Pattern 4 - Version specific regression:
Bug was introduced in a specific version. Use git bisect to find the commit that introduced it.
Response: Tag the issue with the affected version range. Backport the fix to maintenance branches if on LTS version.

Pattern 5 - Environment specific issue:
Works on reporter's machine but not in CI, or works on Linux but not Windows.
Response: Ask for full environment details. Common causes: line ending differences, case-sensitive filesystem, locale settings.

Pattern 6 - Third party library conflict:
The issue is caused by a dependency rather than the project itself.
Response: Document the known conflict in the FAQ. Provide a workaround using dependency exclusions.
Open an issue with the upstream library if it is their bug to fix.

Pattern 7 - Feature request scope creep:
A feature request grows to include many sub-features during discussion.
Response: Create sub-tasks for each discrete piece of work. Implement incrementally across multiple releases.
""",

"version_compatibility_guide.txt": """
Version Compatibility and Migration Guide

Java version compatibility:
Java 8: still widely used, all major Apache and Spring projects support it.
Java 11: LTS version, most modern projects require at minimum Java 11.
Java 17: current LTS, Spring Boot 3.x requires Java 17 minimum.
Java 21: latest LTS with virtual threads (Project Loom). Spring Boot 3.2+ supports virtual threads.

Spring Boot version compatibility:
Spring Boot 2.x supports Java 8, 11, 17. End of OSS support: November 2023.
Spring Boot 3.x requires Java 17+. Uses Jakarta EE 10 (javax.* renamed to jakarta.*).
Common migration issue: javax.persistence.* imports must change to jakarta.persistence.* when upgrading to Spring Boot 3.

Apache project compatibility notes:
Apache Kafka clients are backward compatible with brokers 2 versions older.
Apache Hadoop 3.x is not compatible with Hadoop 2.x HDFS format without migration.
Apache Maven plugins must match the Maven version — check plugin compatibility matrix.

Dependency upgrade guidelines:
Upgrade one major dependency at a time to isolate issues.
Run the full test suite after each upgrade before proceeding to the next.
Check the project migration guide or release notes for known breaking changes.
Use Dependabot or Renovate to automate minor and patch version upgrades.

Hibernate and JPA migrations:
Hibernate 6 (used in Spring Boot 3) changed many default behaviors from Hibernate 5.
Column naming strategy changed — verify your schema still matches after upgrading.
HQL syntax changes in Hibernate 6 — some queries need updating.
""",

"documentation_and_testing_guide.txt": """
Documentation and Testing Standards for Open Source Projects

Writing good bug reports:
Title: concise description of the problem, not the symptom. Bad: 'NPE in my app'. Good: 'NullPointerException in JdbcTemplate when query returns empty ResultSet'.
Description: what you expected to happen, what actually happened.
Reproduction steps: numbered steps that reliably reproduce the issue.
Environment: Java version, OS, project version, build tool version.
Attachments: stack trace, minimal code example, test case that fails.

Writing good feature requests:
Describe the use case, not the implementation. Explain what problem you are trying to solve.
Include examples of how the API would look if the feature were implemented.
Reference similar implementations in other projects if applicable.
Indicate whether you are willing to submit a pull request implementing the feature.

Unit test best practices:
Each test should test one thing. Test names should describe what is being tested.
Use the Arrange-Act-Assert pattern consistently.
Mock external dependencies (databases, HTTP calls) to keep tests fast and deterministic.
Test edge cases: null input, empty collections, maximum values, concurrent access.

Integration test guidelines:
Integration tests verify that components work together correctly.
Use Spring Boot test slices (@WebMvcTest, @DataJpaTest) to test specific layers.
Avoid starting the full application context in tests unless necessary — it is slow.
Use Testcontainers for tests that require a real database or message broker.

Code coverage:
Aim for 80 percent line coverage as a baseline. Coverage above 90 percent often means testing implementation details.
Focus coverage on business logic, not boilerplate.
Use mutation testing (PIT) to verify that tests actually catch bugs, not just execute code.
"""

}

count = 0
for filename, content in DOCS.items():
    path = KB_DIR / filename
    path.write_text(content.strip(), encoding="utf-8")
    print(f"✓ {filename}")
    count += 1

print(f"\nDone — {count} documents written to {KB_DIR.resolve()}")
print("Restart the backend to re-seed ChromaDB.")