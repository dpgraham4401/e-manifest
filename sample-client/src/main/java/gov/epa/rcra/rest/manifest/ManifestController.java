package gov.epa.rcra.rest.manifest;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;

@RestController
@RequestMapping("/api/manifest")
public class ManifestController {

    private final ManifestService manifestService;

    ManifestController(ManifestService manifestService) {
        this.manifestService = manifestService;
    }

    @GetMapping(value = "/{manifestTrackingNumber}", produces = MediaType.APPLICATION_JSON_VALUE)
    public String getManifest(@PathVariable String manifestTrackingNumber) {
        return manifestService.getEmanifest(manifestTrackingNumber);
    }

    @PostMapping(value = "", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<String> createManifest(@RequestPart("file") MultipartFile file,
                                                 @RequestPart("json") String data) throws IOException {
        if (file.isEmpty()) {
            return new ResponseEntity<>("Error", HttpStatus.BAD_REQUEST);
        }
        String result = manifestService.createPaperManifest(file, data);
        return new ResponseEntity<>(result, HttpStatus.CREATED);
    }

    @ExceptionHandler(ManifestException.class)
    public ResponseEntity<String> conflict() {
        return new ResponseEntity<>("Error", HttpStatus.valueOf(404));
    }

}
