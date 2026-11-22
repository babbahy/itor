import org.jetbrains.compose.desktop.application.dsl.TargetFormat

plugins {
    kotlin("jvm") version "2.1.0"
    kotlin("plugin.serialization") version "2.1.0"
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.0"
    id("org.jetbrains.compose") version "1.7.3"
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation(compose.desktop.currentOs)
    implementation(compose.material3)
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-swing:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
}

compose.desktop {
    application {
        mainClass = "itor.MainKt"
        // `gradlew run -Pdemo` shows the demo menu.
        if (project.hasProperty("demo")) args += "--demo"
        // `gradlew run -Pscreen=team` opens that tab first.
        (project.findProperty("screen") as String?)?.let { args += "--screen=$it" }
        nativeDistributions {
            targetFormats(TargetFormat.Msi)
            packageName = "itor"
            packageVersion = "1.0.8"
            description = "itor: working time and IT help, even offline"
            vendor = "itor"
            // Ship the whole Java runtime: avoids missing modules (HTTP client, TLS) in the installed app.
            includeAllModules = true
            // resources/windows/itor-helper/ (built by scripts/build-helper.ps1) is copied next to the app.
            appResourcesRootDir.set(project.layout.projectDirectory.dir("resources"))
            windows {
                perUserInstall = true
                menuGroup = "itor"
                shortcut = true
                menu = true
                upgradeUuid = "6b0b1f8e-5c6e-4c39-9a2b-1d2f0e8b7a41"
                // itor icon for the exe, Start menu shortcut and installer (scripts/make-icon.py).
                iconFile.set(project.file("icons/itor.ico"))
            }
        }
    }
}
