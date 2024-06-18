package gov.epa.rcra.rest.manifest;

import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.multipart.MultipartFile;

@Service
public class ManifestService {

    private final ManifestClient manifestClient;

    ManifestService(ManifestClient manifestClient) {
        this.manifestClient = manifestClient;
    }

    public String getEmanifest(String manifestTrackingNumber) throws ManifestException {
        return manifestClient.getEmanifest(manifestTrackingNumber);
    }

    public String createPaperManifest(MultipartFile file, String data) throws ManifestException {
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("attachment", file);
        body.add("manifest", data);

        System.out.println("ManifestService.createPaperManifest: " + body);
        return "Yes";

//        return manifestClient.createPaperManifest(body);
    }
}
